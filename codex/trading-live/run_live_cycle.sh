#!/bin/zsh

set -euo pipefail

RUN_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$RUN_DIR/logs"
STAMP="$(date +%Y%m%d-%H%M%S)"

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

# Permit execution from 9:40 AM through 3:50 PM Eastern Time.
if (( 10#$TIME_ET < 940 || 10#$TIME_ET > 1550 )); then
  echo "Outside the permitted 9:40 AM–3:50 PM ET window."
  exit 1
fi

# Consume the one-time authorization only after all scheduling checks pass.
rm -f "$RUN_DIR/ARM_ONCE"

codex exec \
  --cd "$RUN_DIR" \
  --ephemeral \
  --sandbox read-only \
  "$(cat "$RUN_DIR/LIVE_RUN.md")" \
  > "$LOG_DIR/$STAMP.out" \
  2> "$LOG_DIR/$STAMP.err"

echo
echo "Live cycle completed."
echo "Result:   $LOG_DIR/$STAMP.out"
echo "Progress: $LOG_DIR/$STAMP.err"