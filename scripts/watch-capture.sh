#!/usr/bin/env bash
LOG="${1:-$(dirname "$0")/../docs/captures/zentraly-traffic.log}"
echo "Watching $LOG (Ctrl+C to stop)"
tail -f "$LOG"
