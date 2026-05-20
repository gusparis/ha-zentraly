#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAN_IP="${LAN_IP:-$(ipconfig getifaddr en0 2>/dev/null || echo 192.168.88.20)}"
MITM_PORT="${MITM_PORT:-8888}"
TEST_PORT="${TEST_PORT:-9999}"

kill $(lsof -t -i :"${MITM_PORT}" -i :"${TEST_PORT}") 2>/dev/null || true
sleep 1

echo "=== Prueba de red (sin proxy) ==="
echo "En el celular, abrí: http://${LAN_IP}:${TEST_PORT}/"
echo "Si NO carga, el problema es red/router (no mitmproxy)."
echo ""

python3 -m http.server "${TEST_PORT}" --bind 0.0.0.0 &
HTTP_PID=$!

cleanup() {
  kill "${HTTP_PID}" 2>/dev/null || true
  kill $(lsof -t -i :"${MITM_PORT}") 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "=== Proxy MITM ==="
echo "Si la prueba anterior SÍ carga, configurá proxy ${LAN_IP}:${MITM_PORT}"
echo "y abrí: http://mitm.it"
echo ""

LAN_IP="${LAN_IP}" MITM_PORT="${MITM_PORT}" exec "${ROOT}/scripts/start-mitm-capture.sh"
