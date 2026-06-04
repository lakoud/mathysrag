#!/bin/bash
# Weekly evaluation script for REMS
# Add to crontab: 0 8 * * 1 /path/to/weekly_evaluation.sh
# This runs every Monday at 8:00 AM

set -e

# Configuration
REMS_DIR="${REMS_DIR:-$(dirname "$0")/..}"
LOG_FILE="${REMS_DIR}/logs/evaluation_$(date +%Y%m%d).log"
EVAL_NAME="Évaluation hebdomadaire $(date +%d/%m/%Y)"

# Create logs directory if it doesn't exist
mkdir -p "${REMS_DIR}/logs"

echo "[$(date)] Starting weekly evaluation..." >> "$LOG_FILE"

# Activate virtual environment if it exists
if [ -d "${REMS_DIR}/.venv" ]; then
    source "${REMS_DIR}/.venv/bin/activate"
fi

# Run evaluation
cd "$REMS_DIR"

# Evaluate interactions from the last 7 days
START_DATE=$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d "7 days ago" +%Y-%m-%d)
END_DATE=$(date +%Y-%m-%d)

uv run rems evaluate \
    --start "$START_DATE" \
    --end "$END_DATE" \
    --name "$EVAL_NAME" \
    --output "${REMS_DIR}/reports" \
    2>&1 | tee -a "$LOG_FILE"

echo "[$(date)] Weekly evaluation completed." >> "$LOG_FILE"
