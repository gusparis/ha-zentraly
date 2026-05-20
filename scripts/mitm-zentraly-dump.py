"""mitmproxy addon: dump full Zentraly API to JSONL immediately."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from mitmproxy import http

HOST = "ztprdrestservicesv2.azurewebsites.net"
OUT = Path(__file__).resolve().parents[1] / "docs" / "captures" / "zentraly-api.jsonl"


def _client(flow: http.HTTPFlow) -> str:
    address = getattr(flow.client_conn, "address", None)
    if address:
        return f"{address[0]}:{address[1]}"
    return "unknown"


def _redact_headers(headers) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in headers.items(multi=True):
        lower = key.lower()
        if lower == "authorization":
            if value.startswith("ztv2Auth"):
                parts = value[len("ztv2Auth") :].split(":")
                result[key] = (
                    f"ztv2Auth"
                    f"<email>:<password>"
                    f" ({len(parts)} parts, lengths={[len(p) for p in parts]})"
                )
            elif value.startswith("ztv2Token"):
                result[key] = f"ztv2Token<redacted len={len(value) - len('ztv2Token')}>"
            else:
                result[key] = "<redacted>"
        elif lower == "firebase":
            try:
                result[key] = json.loads(base64.b64decode(value))
            except (json.JSONDecodeError, ValueError):
                result[key] = value[:200]
        else:
            result[key] = value
    return result


def _body(raw: bytes | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw.decode(errors="replace")[:2000]


class ZentralyDump:
    def response(self, flow: http.HTTPFlow) -> None:
        if HOST not in (flow.request.host or ""):
            return
        if not flow.response:
            return

        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "client": _client(flow),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "request_headers": _redact_headers(flow.request.headers),
            "request_body": _body(flow.request.content),
            "status": flow.response.status_code,
            "response_body": _body(flow.response.content),
        }

        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


addons = [ZentralyDump()]
