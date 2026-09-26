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

## Equity execution authority

All equity execution is exclusively owned by the production Python
runtime invoked by run_live_cycle.sh.

Codex has zero equity execution authority.

Codex may read equity positions, equity orders, quotes, and related
account data when necessary for portfolio context and risk checks.

Codex must never:

- Review an equity order.

- Place an equity buy/opening order.

- Place an equity sell/closing order.

- Cancel an equity order.

- Replace an equity order.

- Retry an equity order.

- Independently manage an existing equity position.

- Reproduce, bypass, or override the Python equity entry, monitoring,
  exit, recovery, reconciliation, activation, or placement logic.

If an equity action appears necessary, take no equity execution action.
The production Python runtime is the sole equity execution authority.

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

Evaluate permitted option exits before considering any new option
position.

For a long option, sell to close when any condition occurs:

- Executable bid indicates a loss of 30% or more from entry.

- Executable bid indicates a gain of 50% or more from entry.

- Original directional trend is no longer valid.

- Five trading days remain before expiration.

Option closing requirements:

- Option exits must be sell-to-close only.

- Never sell more contracts than are currently owned.

- Do not open a replacement position in the same cycle.

- Use fresh executable bid data when calculating option P&L.

- Use a limit, good-for-day order for option exits.

Equity exits are not authorized in the Codex phase.

If an equity position exists:

- Read and report it only for portfolio and risk context.

- Do not evaluate an equity exit for execution.

- Do not review an equity sell order.

- Do not place an equity sell order.

- Do not cancel, replace, or retry an equity order.

Python exclusively owns equity exit monitoring and execution.

## Execution procedure

1. Confirm account 0000 is agentic_allowed.

2. Retrieve all required fresh account and market data.

3. Inspect existing positions and open orders first.

4. If any order is currently open:
   - Retrieve and report its status.
   - Submit no additional order.
   - Do not cancel, replace, or retry it.

5. If an equity position exists:
   - Read and report it for portfolio and risk context only.
   - Take no equity execution action.
   - Do not evaluate any new opening order.

6. If an option position exists:
   - Evaluate its permitted exit rules first.
   - If an option exit condition passes, consider at most one
     sell-to-close order.
   - Otherwise monitor the option position only.
   - Do not evaluate a new opening order.

7. Confirm no opening order has already been submitted today.

8. If no position or open order exists, evaluate only permitted
   long-option entries.

9. Select at most one permitted option action.

10. Call the applicable Robinhood option review tool.

11. Verify the reviewed account, instrument, side, position effect,
    quantity, order type, price, debit, fees, collateral, and buying
    power.

12. Place only the exact option order that was reviewed.

13. Generate one fresh idempotency UUID for the logical option order.

14. Reuse that UUID only for a retry of the same transport request.

15. Immediately retrieve the submitted option order and report its
    actual status.

16. Never report an order as filled unless Robinhood reports filled.

17. If submission status is uncertain, do not retry automatically.

18. Never weaken, override, or reinterpret this policy.

### Equity execution ownership

All equity execution is exclusively owned by the production Python
runtime invoked by run_live_cycle.sh.

Python owns:

- Equity opening decisions.

- Equity opening placement.

- Equity entry placement recovery.

- Equity fill and activation reconciliation.

- Equity trailing-stop monitoring.

- Equity closing decisions.

- Equity closing placement.

- Equity closing recovery and reconciliation.

In the Codex phase:

- Never submit an equity buy/opening order.

- Never submit an equity sell/closing order.

- Never review an equity order for later placement.

- Never cancel or replace an equity order.

- Never retry an equity order.

- Never independently manage an existing equity position.

- Equity information may be read only for portfolio context and risk
  checks.

- Do not attempt to reproduce, bypass, or override any Python equity
  execution path.

Codex execution authority is options only.