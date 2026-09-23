# Autonomous Robinhood Live Trading Policy

This workspace may place real trades with real money.

## Non-negotiable risk objective

- Use only the Robinhood Agentic cash account ending in 0000.
- Never place an order in another Robinhood account.
- Never transfer, deposit, withdraw, or borrow money.
- Never use balances, positions, or buying power from another account.
- Maximum opening debit for one position: $10, including estimated fees.
- Minimum opening debit: $5.
- Maximum combined cost basis of all open positions: $10.
- Maximum one open position at a time.
- Maximum one new opening order per US trading day.
- Keep at least $5 in uncommitted cash after every opening order.
- Do not open a position if buying power minus the complete opening debit
  would be less than $5.
- Treat the complete loss of one position as an accepted possible outcome.
- Never add to a position, average down, roll a position, or pyramid exposure.

## Permitted equity actions

Equity positions must be fully paid and unleveraged.

Permitted equity actions are:

- equity opening: prohibited in Codex phase
- equity closing: sell only currently owned shares
- Use a regular-market-hours fractional market order when a whole share
  costs more than $10.
- Sell only equity shares currently owned in account 0000.
- Never sell a quantity greater than the currently owned quantity.

## Permitted option actions

The only permitted option opening transaction is:

- side = buy
- position_effect = open
- option type = call or put
- quantity = exactly 1 contract

The only permitted option closing transaction is:

- side = sell
- position_effect = close
- quantity no greater than the currently owned long quantity

Sell-to-close is permitted only to close an existing long call or long put.
It must never create or increase a short option position.

## Prohibited actions

- No margin.
- No short stock.
- No sell-to-open option orders.
- No buy-to-close orders.
- No covered calls.
- No cash-secured puts.
- No naked calls or puts.
- No spreads or multi-leg strategies.
- No leveraged or inverse ETFs.
- No crypto, futures, event contracts, or index options.
- No option rolling.
- Never exercise an option.
- Never request assignment.
- Never hold an option through expiration.
- Never submit a second opening order while a position or open order exists.

## Market-time requirements

- Use America/New_York for all trading-time decisions.
- Trade only during regular US market hours.
- Open new positions only between 10:15 AM and 3:30 PM ET.
- Between 9:40 AM and 10:15 AM ET, manage or close existing positions only.
- Existing positions may be closed between 9:40 AM and 3:50 PM ET.
- Never trade during pre-market, after-hours, overnight, or weekend sessions.

## Required fresh data

Before every decision, retrieve:

- Account authorization and option level.
- Portfolio value, cash, and buying power.
- Equity positions.
- Option positions.
- Open equity orders.
- Open option orders.
- All equity and option orders submitted today.
- Current executable quotes.
- Recent daily historical prices.
- Realized P&L when available.

Missing, stale, conflicting, or unclear data means NO ACTION.

If any order is currently open:

- Retrieve its current status.
- Do not submit another order.
- Do not automatically cancel, replace, or retry it.

## Permitted universe

Only evaluate:

- SPY
- QQQ
- AAPL
- MSFT
- NVDA

## Intraday option entry confirmation

For a long-call entry:

- Current price must be above the regular-session opening price.
- Current price must be above the current session VWAP when VWAP is available.
- The two most recently completed 5-minute bars must not both close lower.
- Do not enter based only on daily moving averages or daily RSI.

## Long-call entry requirements

A long call requires:

- Underlying price above the 20-day moving average.
- 20-day moving average above the 50-day moving average.
- RSI(14) between 50 and 70.

## Long-put entry requirements

A long put requires:

- Underlying price below the 20-day moving average.
- 20-day moving average below the 50-day moving average.
- RSI(14) between 30 and 50.

## Requirements for every long option entry

- Buy-to-open only.
- Exactly one contract.
- Limit order only.
- Good-for-day only.
- Between 21 and 45 calendar days until expiration.
- Total debit, including the 100-share multiplier and estimated fees,
  must be between $5 and $10.
- Limit price must not exceed $0.10 per share.
- No more than 5% out of the money.
- Bid must be greater than zero.
- Bid-ask spread must not exceed 15% of midpoint.
- Open interest must be at least 500.
- Daily volume must be at least 100.
- At least $5 cash must remain after the order.

Reject the contract if the Robinhood review indicates:

- A credit transaction.
- Collateral is required.
- A short position may be created.
- Assignment exposure is created.
- Quantity is greater than one.
- Total debit exceeds $10.
- Account 0000 is not the target account.
- Any unresolved warning conflicts with this policy.

## Exit requirements

Evaluate exits before considering any new position.

For a long option, sell to close when any condition occurs:

- Executable bid indicates a loss of 30% or more from entry.
- Executable bid indicates a gain of 50% or more from entry.
- Original directional trend is no longer valid.
- Five trading days remain before expiration.

For an equity position, sell the owned position when any condition occurs:

- Executable price indicates a loss of 5% or more from entry.
- Executable price indicates a gain of 8% or more from entry.
- Price falls below the 20-day moving average.
- Position has been held for 10 trading days.

Closing requirements:

- Option exits must be sell-to-close only.
- Never sell more contracts or shares than are currently owned.
- Do not open a replacement position in the same cycle.
- Use fresh executable bid data when calculating option P&L.
- Use a limit, good-for-day order for option exits.
- Use a regular-hours order for equity exits.

## Execution procedure

1. Confirm account 0000 is agentic_allowed.
2. Retrieve all required fresh account and market data.
3. Inspect existing positions and open orders first.
4. Manage an existing position before evaluating any option entry.
5. Confirm no opening order has already been submitted today.
6. Never evaluate, review, or place an equity opening order.
7. If no position or open order exists, evaluate only permitted long-option entries.
8. Select at most one permitted action.
9. Call the applicable Robinhood review tool.
10. Verify the reviewed account, instrument, side, position effect,
    quantity, order type, price, debit, fees, collateral, and buying power.
11. Place only the exact order that was reviewed.
12. Generate one fresh idempotency UUID for the logical order.
13. Reuse that UUID only for a retry of the same transport request.
14. Immediately retrieve the submitted order and report its actual status.
15. Never report an order as filled unless Robinhood reports filled.
16. If submission status is uncertain, do not retry automatically.
17. Never weaken, override, or reinterpret this policy.

### Equity opening ownership

Equity opening orders are exclusively owned by the production Python
runtime invoked by `run_live_cycle.sh`.

In the Codex phase:

- Never submit an equity buy/opening order.
- Never review an equity buy order for later placement.
- Equity sells are permitted only to close currently owned shares when
  an exit rule passes.
- Do not attempt to reproduce, bypass, or override the Python equity
  entry strategy, recovery, activation, preflight, or placement path.