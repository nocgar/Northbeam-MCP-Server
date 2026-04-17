#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/daily-report.log"

echo "=== Northbeam Daily Report: $(date) ===" >> "$LOG_FILE"
python3 "$SCRIPT_DIR/northbeam_report.py" >> "$LOG_FILE" 2>&1
echo "=== Done: $(date) ===" >> "$LOG_FILE"
