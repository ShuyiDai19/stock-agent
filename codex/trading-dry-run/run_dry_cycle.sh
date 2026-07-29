#!/bin/zsh

set -euo pipefail

RUN_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$RUN_DIR/logs"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$LOG_DIR"

codex exec \
  --cd "$RUN_DIR" \
  --ephemeral \
  --sandbox read-only \
  "$(cat "$RUN_DIR/DRY_RUN.md")" \
  > "$LOG_DIR/$STAMP.out" \
  2> "$LOG_DIR/$STAMP.err"

echo
echo "Dry run completed."
echo "Result:   $LOG_DIR/$STAMP.out"
echo "Progress: $LOG_DIR/$STAMP.err"
