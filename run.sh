#!/bin/bash
export BOTS_DIR="$HOME/wolfhost/bots"
export LOGS_DIR="$HOME/wolfhost/logs"
export DATA_DIR="$HOME/wolfhost/data"
export TMP_DIR="$HOME/wolfhost/tmp"
export DATABASE_URL="sqlite+aiosqlite:///$HOME/wolfhost/data/wolfhost.db"

mkdir -p "$BOTS_DIR" "$LOGS_DIR" "$DATA_DIR" "$TMP_DIR"

cd /home/runner/workspace/wolf-host
python -m uvicorn main:app --host 0.0.0.0 --port 8000
