#!/bin/zsh

set -euo pipefail

RUN_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$RUN_DIR/../.." && pwd)"

LOG_DIR="$RUN_DIR/logs"
STAMP="$(date +%Y%m%d-%H%M%S)"

EQUITY_OUT="$LOG_DIR/$STAMP.equity.out"
EQUITY_ERR="$LOG_DIR/$STAMP.equity.err"

CODEX_OUT="$LOG_DIR/$STAMP.codex.out"
CODEX_ERR="$LOG_DIR/$STAMP.codex.err"

mkdir -p "$LOG_DIR"

if [[ -f "$RUN_DIR/STOP" ]]; then
  echo "Live trading is stopped by STOP file."
  exit 1
fi

if [[ ! -f "$RUN_DIR/ARM_ONCE" ]]; then
  echo "Not armed. Create ARM_ONCE before running a live cycle."
  exit 1
fi

WEEKDAY="$(TZ=America/New_York date +%u)"
TIME_ET="$(TZ=America/New_York date +%H%M)"

if (( WEEKDAY > 5 )); then
  echo "Outside a US trading weekday."
  exit 1
fi

# Permit management from 9:40 AM through 3:50 PM Eastern Time.
if (( 10#$TIME_ET < 940 || 10#$TIME_ET > 1550 )); then
  echo "Outside the permitted 9:40 AM–3:50 PM ET window."
  exit 1
fi

# Consume one-time authorization before any component can place an order.
rm -f "$RUN_DIR/ARM_ONCE"

echo "Running Python equity-entry runtime..."

if ! (
  cd "$REPO_ROOT"

  PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
    python -m stock_agent.runners.robinhood_equity_cycle
) > "$EQUITY_OUT" 2> "$EQUITY_ERR"; then
  echo "Equity-entry runtime failed safely."
  echo "Result:   $EQUITY_OUT"
  echo "Progress: $EQUITY_ERR"
  exit 1
fi

EQUITY_RESULT="$(
  tail -n 1 "$EQUITY_OUT"
)"

case "$EQUITY_RESULT" in
  "EQUITY ENTRY CYCLE RESULT: OPENING ORDER SUBMITTED")
    echo
    echo "Live cycle completed."
    echo "$EQUITY_RESULT"
    echo "Equity result:   $EQUITY_OUT"
    echo "Equity progress: $EQUITY_ERR"
    exit 0
    ;;

  "EQUITY ENTRY CYCLE RESULT: NO ACTION")
    echo "No equity opening submitted."
    echo "Continuing to Codex management/options phase."
    ;;

  "EQUITY ENTRY CYCLE RESULT: REVIEW ONLY")
    echo "Live cycle failed safely: runtime was not LIVE."
    echo "Equity result:   $EQUITY_OUT"
    echo "Equity progress: $EQUITY_ERR"
    exit 1
    ;;

  *)
    echo "Live cycle failed safely: unexpected equity runtime result."
    echo "Received: $EQUITY_RESULT"
    echo "Equity result:   $EQUITY_OUT"
    echo "Equity progress: $EQUITY_ERR"
    exit 1
    ;;
esac

codex exec \
  --cd "$RUN_DIR" \
  --ephemeral \
  --sandbox read-only \
  "$(cat "$RUN_DIR/LIVE_RUN.md")" \
  > "$CODEX_OUT" \
  2> "$CODEX_ERR"

echo
echo "Live cycle completed."
echo "Equity result:   $EQUITY_OUT"
echo "Equity progress: $EQUITY_ERR"
echo "Codex result:    $CODEX_OUT"
echo "Codex progress:  $CODEX_ERR"