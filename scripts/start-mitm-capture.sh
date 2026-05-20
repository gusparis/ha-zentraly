#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAPTURE_DIR="$ROOT/docs/captures"
STAMP="$(date +%Y%m%d-%H%M%S)"
FLOW_FILE="$CAPTURE_DIR/zentraly-${STAMP}.flow"
LOG_FILE="$CAPTURE_DIR/zentraly-api.jsonl"
LAN_IP="${LAN_IP:-$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 192.168.88.20)}"
PORT="${MITM_PORT:-8888}"

mkdir -p "$CAPTURE_DIR"
: > "$LOG_FILE" 2>/dev/null || true

echo "Zentraly MITM capture"
echo "  Mac IP:     $LAN_IP"
echo "  Proxy port: $PORT"
echo "  Flow file:  $FLOW_FILE"
echo "  API dump:   $LOG_FILE"
echo ""
echo "Celular — proxy MANUAL en Wi-Fi (HTTP y HTTPS si iOS lo muestra):"
echo "  Servidor: $LAN_IP   Puerto: $PORT"
echo "  En Safari escribí: http://mitm.it"
echo "  NO abras http://${LAN_IP}:${PORT}/ en la barra de direcciones (eso genera un bucle)."
echo ""
echo "Si mitm.it dice 'traffic is NOT going through mitmproxy':"
echo "  el celular NO usa el proxy (VPN activa, proxy mal puesto, o firewall Mac)."
echo ""
echo "Mac — desactivá VPN (Surfshark/etc) y NO pongas proxy en el Mac, solo en el celular."
echo "Firewall Mac: permitir Python/mitmdump entrante o desactivar temporalmente."
echo ""

exec mitmdump \
  --listen-host 0.0.0.0 \
  --listen-port "$PORT" \
  --set block_global=false \
  --set confdir="$HOME/.mitmproxy" \
  --flow-detail 1 \
  -w "$FLOW_FILE" \
  -s "$ROOT/scripts/mitm-zentraly-dump.py"
