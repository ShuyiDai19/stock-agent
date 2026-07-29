Use the robinhood-trading MCP to run exactly one autonomous live trading cycle.

Read and obey AGENTS.override.md completely.

This is a one-time live cycle, not a continuously running process.

The task is authorized to place at most one real order without interactive
confirmation, but only when every requirement in AGENTS.override.md passes.

Execution order:

1. Confirm the Agentic cash account ending in 0000.
2. Retrieve fresh portfolio, buying power, positions, open orders,
   today's orders, quotes, and historical data.
3. If an order is currently open:
   - Retrieve and report its current status.
   - Submit no additional order.
4. If a position exists:
   - Evaluate all exit requirements first.
   - If an exit condition passes, review and submit at most one exact
     closing order.
   - Do not evaluate or submit a new opening order.
5. If there is no position and no open order:
   - Confirm no opening order has already been submitted today.
   - Evaluate the permitted universe.
   - Submit at most one qualifying opening order.
6. For options, permit only:
   - buy + open for one long call or long put
   - sell + close for a currently owned long call or long put
7. Always review the exact order immediately before placement.
8. Place only the exact order that was reviewed.
9. Retrieve and report the submitted order's actual status.
10. Never retry automatically after an uncertain placement result.

End with exactly one of:

LIVE CYCLE RESULT: NO ACTION
LIVE CYCLE RESULT: OPEN ORDER MONITORED
LIVE CYCLE RESULT: OPENING ORDER SUBMITTED
LIVE CYCLE RESULT: CLOSING ORDER SUBMITTED
LIVE CYCLE RESULT: FAILED SAFELY