Use the robinhood-trading MCP to run exactly one autonomous live
management/options cycle.

Read and obey AGENTS.override.md completely.

This phase runs only after the production Python equity-entry runtime
completed without submitting an equity opening order.

The Python runtime exclusively owns all equity opening decisions and
equity opening placement.

You are NOT authorized to open an equity position.

Never review or place an equity BUY/opening order.

This is a one-time live cycle, not a continuously running process.

The task is authorized to place at most one real order without
interactive confirmation, but only when every applicable requirement in
AGENTS.override.md passes.

Execution order:

1. Confirm the Agentic cash account ending in 0000.

2. Retrieve fresh portfolio, buying power, positions, open orders,
   today's orders, quotes, and historical data required for this phase.

3. If any order is currently open:
   - Retrieve and report its current status.
   - Submit no additional order.

4. If an existing equity or option position exists:
   - Evaluate all applicable exit requirements first.
   - If an exit condition passes, review and submit at most one exact
     closing order.
   - Do not evaluate or submit any new opening order.
   - If no exit condition passes, monitor the position only.

5. If there is no position and no open order:
   - Confirm no opening order has already been submitted today.
   - Equity opening is prohibited in this Codex phase.
   - You may evaluate an OPTIONS opening only when every options rule
     in AGENTS.override.md passes.

6. For options, permit only:
   - buy + open for one long call or long put
   - sell + close for a currently owned long call or long put

7. For equities, permit only:
   - sell + close of currently owned shares when an exit rule passes
   - never buy/open an equity position

8. Always review the exact permitted order immediately before
   placement.

9. Place only the exact order that was reviewed.

10. Retrieve and report the submitted order's actual status.

11. Never retry automatically after an uncertain placement result.

12. Submit at most one real order in this Codex phase.

End with exactly one of:

LIVE CYCLE RESULT: NO ACTION
LIVE CYCLE RESULT: POSITION MONITORED
LIVE CYCLE RESULT: OPEN ORDER MONITORED
LIVE CYCLE RESULT: OPTION OPENING ORDER SUBMITTED
LIVE CYCLE RESULT: CLOSING ORDER SUBMITTED
LIVE CYCLE RESULT: FAILED SAFELY