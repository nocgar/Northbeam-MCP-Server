#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$SCRIPT_DIR/daily-report-prompt.txt"
LOG_FILE="$SCRIPT_DIR/daily-report.log"

echo "=== Northbeam Daily Report: $(date) ===" >> "$LOG_FILE"

/opt/node22/bin/claude \
  --dangerously-skip-permissions \
  -p "$(cat "$PROMPT_FILE")" \
  >> "$LOG_FILE" 2>&1

echo "=== Done: $(date) ===" >> "$LOG_FILE"
