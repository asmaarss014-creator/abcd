#!/data/data/com.termux/files/usr/bin/bash
cd "$(dirname "$0")/.."
termux-wake-lock 2>/dev/null || true
python server/server.py
