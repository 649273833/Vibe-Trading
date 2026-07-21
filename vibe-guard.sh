#!/bin/bash
# Vibe-Trading auto-restart wrapper
VENV=/Users/zhanzhiwei/data/test/Vibe-Trading/.venv
PORT=8899

source "$VENV/bin/activate"

while true; do
    # Kill anything still holding the port before starting
    lsof -ti :"$PORT" 2>/dev/null | xargs kill -9 2>/dev/null
    sleep 1

    echo "[$(date '+%H:%M:%S')] Starting Vibe-Trading on :$PORT..."
    vibe-trading serve --port "$PORT" 2>&1
    EXIT=$?
    echo "[$(date '+%H:%M:%S')] Server exited with code $EXIT, restarting in 3s..."
    sleep 3
done
