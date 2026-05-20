"""mitmproxy addon: log Zentraly / Azure API traffic to a readable file."""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[1] / "docs" / "captures" / "zentraly-traffic.log"

HOST_PATTERNS = (
    "ztprdrestservicesv2.azurewebsites.net",
    "azurewebsites.net",
    "zentraly",
    "firebase",
    "googleapis.com",
    "google.com",
)

REDACT_AUTHORIZATION = re.compile(r"(ztv2(?:Auth|Token))(.+)", re.IGNORECASE)


def _matches(host: str) -> bool:
    if not host:
        return False
    return True


def _safe_headers(headers) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in headers.items(multi=True):
        lower = key.lower()
        if lower == "authorization":
            match = REDACT_AUTHORIZATION.match(value)
            if match:
                prefix, rest = match.group(1), match.group(2)
                result[key] = f"{prefix}***redacted*** (len={len(rest)})"
            else:
                result[key] = "***redacted***"
        elif lower == "firebase":
            try:
                decoded = json.loads(base64.b64decode(value))
                result[key] = json.dumps(decoded, ensure_ascii=False)
            except (json.JSONDecodeError, ValueError):
                result[key] = value[:120] + "…"
        else:
            result[key] = value
    return result


def _append_block(text: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(text)


class ZentralyLogger:
    def response(self, flow):
        if not flow.response:
            return

        host = flow.request.host or ""
        if not _matches(host):
            return

        client = getattr(flow.client_conn, "address", None)
        client_label = f"{client[0]}:{client[1]}" if client else "unknown"

        timestamp = datetime.now(timezone.utc).isoformat()
        lines = [
            "",
            "=" * 72,
            f"[{timestamp}] client={client_label} {flow.request.method} {flow.request.pretty_url}",
            f"Status: {flow.response.status_code}",
            "--- Request headers ---",
            json.dumps(_safe_headers(flow.request.headers), indent=2, ensure_ascii=False),
        ]

        if flow.request.content:
            try:
                body = json.loads(flow.request.content)
                lines.append("--- Request JSON ---")
                lines.append(json.dumps(body, indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                lines.append("--- Request body (raw) ---")
                lines.append(flow.request.content[:2000].decode(errors="replace"))

        if flow.response.content:
            try:
                body = json.loads(flow.response.content)
                lines.append("--- Response JSON ---")
                lines.append(json.dumps(body, indent=2, ensure_ascii=False)[:8000])
            except json.JSONDecodeError:
                lines.append("--- Response body (raw) ---")
                lines.append(flow.response.content[:2000].decode(errors="replace"))

        _append_block("\n".join(lines) + "\n")


addons = [ZentralyLogger()]
