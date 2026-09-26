Use the robinhood-trading MCP to run exactly one autonomous live
options-management cycle.

Read and obey AGENTS.override.md completely.

This phase runs only after the production Python equity runtime
completed with:

EQUITY ENTRY CYCLE RESULT: NO ACTION

The production Python runtime exclusively owns all equity execution.

Python owns:
- equity opening decisions and placement
- equity closing decisions and placement
- equity trailing-stop monitoring
- equity placement recovery
- equity fill and activation reconciliation
- equity closing reconciliation

Codex has zero equity execution authority.

Codex may read equity positions, equity orders, quotes, and account data
when required for portfolio context or risk checks.

Codex MUST NOT:
- review an equity order
- place an equity BUY
- place an equity SELL
- open an equity position
- close an equity position
- cancel or replace an equity order
- retry an equity order
- independently manage an equity position

Codex execution authority is OPTIONS ONLY.

This is a one-time live cycle, not a continuously running process.

The task is authorized to place at most one real option order without
interactive confirmation, but only when every applicable requirement in
AGENTS.override.md passes.

Execution order:

1. Confirm the Agentic cash account ending in 0000.

2. Retrieve fresh portfolio, buying power, positions, open orders,
   today's orders, quotes, and historical data required for this phase.

3. If any order is currently open:
   - Retrieve and report its current status.
   - Submit no additional order.
   - Do not cancel, replace, or retry it.

4. If an existing equity position exists:
   - Read and report it for portfolio and risk context only.
   - Take no equity execution action.
   - Do not evaluate, review, or place an equity closing order.
   - Do not evaluate or submit any new opening order.

5. If an existing option position exists:
   - Evaluate all applicable option exit requirements first.
   - If an option exit condition passes, review and submit at most one
     exact sell-to-close order.
   - Do not evaluate or submit any new opening order.
   - If no exit condition passes, monitor the option position only.

6. If there is no position and no open order:
   - Confirm no opening order has already been submitted today.
   - You may evaluate an OPTIONS opening only when every options rule
     in AGENTS.override.md passes.

7. For options, permit only:
   - buy + open for one long call or long put
   - sell + close for a currently owned long call or long put

8. Always review the exact permitted option order immediately before
   placement.

9. Place only the exact option order that was reviewed.

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