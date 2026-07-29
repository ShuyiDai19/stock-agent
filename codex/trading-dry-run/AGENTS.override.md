# Robinhood Automated Dry-Run Policy

This workspace is strictly for automated dry-run analysis.

## Account

- Use only the Robinhood Agentic cash account ending in 0000.
- Do not use another account's cash, buying power, positions, or orders
  when evaluating available capital.
- Confirm account scope using fresh data during every run.

## Permitted actions

- Read account and market data.
- Analyze stocks, ETFs, and long call/put candidates.
- Simulate or review at most one hypothetical order.

## Prohibited actions

- Never place or submit a real order.
- Never cancel, replace, modify, or exercise an order.
- Never transfer, deposit, or withdraw money.
- Never use margin, short stock, short options, spreads, covered calls,
  cash-secured puts, leveraged ETFs, or inverse ETFs.
- Never attempt to work around an unavailable or disabled tool.

## Dry-run limits

- Maximum hypothetical cost: $10.
- Limit orders only.
- At most one hypothetical opening order.
- Long calls and puts must cost no more than $10 after the 100-share multiplier.
- Options must have 14 to 45 calendar days until expiration.
- Reject options with a zero bid.
- Reject options whose bid-ask spread exceeds 15% of midpoint.
- Reject options with open interest below 500 or daily volume below 100.
- Reject options more than 5% out of the money.
- Missing, stale, conflicting, or unclear data means NO TRADE.

## Output

End every run with exactly one of:

DRY RUN RESULT: PREVIEWED — NOT SUBMITTED
DRY RUN RESULT: NO TRADE
DRY RUN RESULT: FAILED SAFELY
