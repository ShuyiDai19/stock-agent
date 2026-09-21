from dataclasses import dataclass
from decimal import (
    Decimal,
    InvalidOperation,
)
from typing import Any

from stock_agent.brokers.robinhood.mcp import (
    MCPToolInvoker,
)
from stock_agent.strategy.universe import (
    EquityUniverseScreenOutcome,
    EquityUniverseScreeningPolicy,
    EquityUniverseSnapshot,
    screen_equity_universe,
)


ROBINHOOD_FUNDAMENTALS_BATCH_SIZE = 10


class RobinhoodUniverseSymbolNotFoundError(
    ValueError
):
    pass


@dataclass(frozen=True, slots=True)
class RobinhoodUniverseLoadItem:
    symbol: str

    snapshot: (
        EquityUniverseSnapshot
        | None
    ) = None

    error: Exception | None = None

    def __post_init__(
        self,
    ) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol cannot be empty"
            )

        succeeded = (
            self.snapshot is not None
            and self.error is None
        )

        failed = (
            self.snapshot is None
            and self.error is not None
        )

        if not (
            succeeded
            or failed
        ):
            raise ValueError(
                "universe load item must "
                "be successful or failed"
            )

    @property
    def succeeded(
        self,
    ) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class RobinhoodUniverseLoadOutcome:
    items: tuple[
        RobinhoodUniverseLoadItem,
        ...,
    ]

    @property
    def snapshots(
        self,
    ) -> tuple[
        EquityUniverseSnapshot,
        ...,
    ]:
        return tuple(
            item.snapshot
            for item in self.items
            if item.snapshot is not None
        )

    @property
    def errors(
        self,
    ) -> tuple[
        RobinhoodUniverseLoadItem,
        ...,
    ]:
        return tuple(
            item
            for item in self.items
            if item.error is not None
        )

    @property
    def snapshot_count(
        self,
    ) -> int:
        return len(
            self.snapshots
        )

    @property
    def error_count(
        self,
    ) -> int:
        return len(
            self.errors
        )


@dataclass(frozen=True, slots=True)
class RobinhoodUniverseScreenOutcome:
    loading: RobinhoodUniverseLoadOutcome
    screening: EquityUniverseScreenOutcome

    @property
    def eligible_symbols(
        self,
    ) -> tuple[
        str,
        ...,
    ]:
        return (
            self.screening
            .eligible_symbols
        )

    @property
    def load_errors(
        self,
    ) -> tuple[
        RobinhoodUniverseLoadItem,
        ...,
    ]:
        return (
            self.loading
            .errors
        )

    @property
    def rejected_items(
        self,
    ):
        return (
            self.screening
            .rejected_items
        )

    @property
    def selected_symbols(
        self,
    ) -> tuple[
        str,
        ...,
    ]:
        return (
            self.screening
            .selected_symbols
        )


    @property
    def deferred_items(
        self,
    ):
        return (
            self.screening
            .deferred_items
        )


def _parse_nonnegative_decimal(
    value: Any,
    *,
    field_name: str,
) -> Decimal:
    if value is None:
        raise ValueError(
            f"{field_name} is missing"
        )

    try:
        parsed = Decimal(
            str(value)
        )
    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise ValueError(
            f"{field_name} is invalid"
        ) from exc

    if not parsed.is_finite():
        raise ValueError(
            f"{field_name} must be finite"
        )

    if parsed < 0:
        raise ValueError(
            f"{field_name} cannot be negative"
        )

    return parsed


def decode_robinhood_equity_universe_batch(
    raw_result: Any,
    *,
    requested_symbols: tuple[
        str,
        ...,
    ],
) -> tuple[
    RobinhoodUniverseLoadItem,
    ...,
]:
    if not isinstance(
        raw_result,
        dict,
    ):
        raise ValueError(
            "Robinhood fundamentals result "
            "must be a mapping"
        )

    data = raw_result.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Robinhood fundamentals result "
            "must contain data"
        )

    raw_results = data.get(
        "results"
    )

    if not isinstance(
        raw_results,
        list,
    ):
        raise ValueError(
            "Robinhood fundamentals result "
            "must contain results"
        )

    raw_not_found = data.get(
        "not_found",
        [],
    )

    if not isinstance(
        raw_not_found,
        list,
    ):
        raise ValueError(
            "Robinhood fundamentals "
            "not_found must be a list"
        )

    requested_set = set(
        requested_symbols
    )

    not_found = set()

    for symbol in raw_not_found:
        if (
            not isinstance(
                symbol,
                str,
            )
            or not symbol.strip()
        ):
            raise ValueError(
                "Robinhood fundamentals "
                "not_found symbols must "
                "be nonempty strings"
            )

        if symbol not in requested_set:
            raise ValueError(
                "Robinhood fundamentals "
                "returned unexpected "
                "not_found symbol"
            )

        not_found.add(
            symbol
        )

    result_by_symbol = {}

    for raw_item in raw_results:
        if not isinstance(
            raw_item,
            dict,
        ):
            raise ValueError(
                "Robinhood fundamentals "
                "entry must be a mapping"
            )

        symbol = raw_item.get(
            "symbol"
        )

        if (
            not isinstance(
                symbol,
                str,
            )
            or not symbol.strip()
        ):
            raise ValueError(
                "Robinhood fundamentals "
                "entry must contain symbol"
            )

        if symbol not in requested_set:
            raise ValueError(
                "Robinhood fundamentals "
                "returned unexpected symbol"
            )

        if symbol in result_by_symbol:
            raise ValueError(
                "Robinhood fundamentals "
                "returned duplicate symbol"
            )

        if symbol in not_found:
            raise ValueError(
                "Robinhood fundamentals "
                "symbol cannot appear in both "
                "results and not_found"
            )

        result_by_symbol[
            symbol
        ] = raw_item

    items = []

    for symbol in requested_symbols:
        if symbol in not_found:
            items.append(
                RobinhoodUniverseLoadItem(
                    symbol=symbol,
                    error=(
                        RobinhoodUniverseSymbolNotFoundError(
                            f"no fundamentals "
                            f"found for {symbol}"
                        )
                    ),
                )
            )

            continue

        raw_item = (
            result_by_symbol.get(
                symbol
            )
        )

        if raw_item is None:
            items.append(
                RobinhoodUniverseLoadItem(
                    symbol=symbol,
                    error=ValueError(
                        "Robinhood fundamentals "
                        f"did not return {symbol}"
                    ),
                )
            )

            continue

        try:
            snapshot = (
                EquityUniverseSnapshot(
                    symbol=symbol,
                    average_volume_30d=(
                        _parse_nonnegative_decimal(
                            raw_item.get(
                                "average_volume_30_days"
                            ),
                            field_name=(
                                "average_volume_30_days"
                            ),
                        )
                    ),
                    market_cap=(
                        _parse_nonnegative_decimal(
                            raw_item.get(
                                "market_cap"
                            ),
                            field_name=(
                                "market_cap"
                            ),
                        )
                    ),
                )
            )

        except Exception as error:
            items.append(
                RobinhoodUniverseLoadItem(
                    symbol=symbol,
                    error=error,
                )
            )

            continue

        items.append(
            RobinhoodUniverseLoadItem(
                symbol=symbol,
                snapshot=snapshot,
            )
        )

    return tuple(
        items
    )


def load_robinhood_equity_universe(
    invoker: MCPToolInvoker,
    *,
    symbols: tuple[
        str,
        ...,
    ],
) -> RobinhoodUniverseLoadOutcome:
    seen_symbols = set()

    for symbol in symbols:
        if not symbol.strip():
            raise ValueError(
                "symbols cannot contain "
                "empty values"
            )

        if symbol != symbol.upper():
            raise ValueError(
                "symbols must be uppercase"
            )

        if symbol in seen_symbols:
            raise ValueError(
                "symbols cannot contain "
                "duplicates"
            )

        seen_symbols.add(
            symbol
        )

    items = []

    for start in range(
        0,
        len(symbols),
        ROBINHOOD_FUNDAMENTALS_BATCH_SIZE,
    ):
        batch = symbols[
            start:
            (
                start
                + ROBINHOOD_FUNDAMENTALS_BATCH_SIZE
            )
        ]

        try:
            raw_result = invoker.call_tool(
                "get_equity_fundamentals",
                {
                    "symbols": list(
                        batch
                    ),
                    "bounds": "regular",
                },
            )

            batch_items = (
                decode_robinhood_equity_universe_batch(
                    raw_result,
                    requested_symbols=batch,
                )
            )

        except Exception as error:
            items.extend(
                RobinhoodUniverseLoadItem(
                    symbol=symbol,
                    error=error,
                )
                for symbol in batch
            )

            continue

        items.extend(
            batch_items
        )

    return RobinhoodUniverseLoadOutcome(
        items=tuple(
            items
        )
    )


def load_and_screen_robinhood_equity_universe(
    invoker: MCPToolInvoker,
    *,
    symbols: tuple[
        str,
        ...,
    ],
    policy: EquityUniverseScreeningPolicy,
) -> RobinhoodUniverseScreenOutcome:
    loading = (
        load_robinhood_equity_universe(
            invoker,
            symbols=symbols,
        )
    )

    screening = (
        screen_equity_universe(
            loading.snapshots,
            policy=policy,
        )
    )

    return RobinhoodUniverseScreenOutcome(
        loading=loading,
        screening=screening,
    )