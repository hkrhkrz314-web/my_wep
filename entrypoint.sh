#!/bin/bash
#===================================================================
# Project: Wolf Host - Private Bot Hosting Dashboard
# Author: White Wolf
# Telegram: https://t.me/j49_c
# Year: 2026
# License: MIT
# Description: Optimized for Hugging Face Spaces & Cloudflare Proxy
#===================================================================
set -e

echo "========================================="
echo "  Wolf Host v2.0 - Private Bot Dashboard"
echo "  Author: White Wolf"
echo "  https://t.me/j49_c"
echo "========================================="

mkdir -p /app/bots /app/logs /app/data /app/tmp

echo "[*] Checking PHP..."
php -v || { echo "ERROR: PHP not found!"; exit 1; }

echo "[*] Checking Composer..."
composer --version || { echo "ERROR: Composer not found!"; exit 1; }

echo "[*] Checking Python..."
python --version || { echo "ERROR: Python not found!"; exit 1; }

echo "[*] Checking pip..."
pip --version || { echo "ERROR: pip not found!"; exit 1; }

echo "[*] Environment:"
echo "    USER: $(whoami)"
echo "    ADMIN_USERNAME: ${ADMIN_USERNAME:-wolf}"
echo "    BOTS_DIR: /app/bots"
echo "    LOGS_DIR: /app/logs"
echo "    DATA_DIR: /app/data"

echo ""
echo "[*] Starting Wolf Host on port 7860..."
exec python -m uvicorn main:app --host 0.0.0.0 --port 7860 --log-level info
