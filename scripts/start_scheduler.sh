#!/bin/bash
# Start the daily scheduler daemon
# Usage: ./scripts/start_scheduler.sh

cd "$(dirname "$0")/.."

echo "Starting Social Media Automation Scheduler..."
echo "Press Ctrl+C to stop."
echo ""

.venv/bin/python -m src.scheduler.daily_scheduler
