"""Helpers to inspect Zentraly login payloads without leaking secrets."""

from __future__ import annotations

import base64
import json
from typing import Any

_REDACT_KEYS = frozenset(
    {
        "ivstrtoken",
        "password",
        "ivstruserfbtoken",
        "authorization",
    }
)


def decode_firebase_header(header_value: str) -> dict[str, Any] | str:
    try:
        return json.loads(base64.b64decode(header_value))
    except (json.JSONDecodeError, ValueError):
        return header_value


def redact_value(key: str, value: Any) -> Any:
    if isinstance(value, dict):
        return redact_structure(value)
    if isinstance(value, list):
        return [redact_structure(item) if isinstance(item, dict) else item for item in value]
    key_lower = key.lower()
    if any(fragment in key_lower for fragment in _REDACT_KEYS):
        if isinstance(value, str) and len(value) > 8:
            return f"{value[:4]}…{value[-4:]} (len={len(value)})"
        return "***"
    return value


def redact_structure(data: dict[str, Any]) -> dict[str, Any]:
    return {key: redact_value(key, value) for key, value in data.items()}


def collect_key_paths(data: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else key
            paths.append(path)
            paths.extend(collect_key_paths(value, path))
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        paths.extend(collect_key_paths(data[0], f"{prefix}[]"))
    return paths


def format_login_inspection(login_result: dict[str, Any], firebase_header: str) -> str:
    lines = ["=== Zentraly login inspection (redacted) ===", ""]
    lines.append(f"numStatus: {login_result.get('numStatus')}")
    io_data = login_result.get("ioData", {})
    if isinstance(io_data, str):
        try:
            io_data = json.loads(io_data)
        except json.JSONDecodeError:
            io_data = {"raw": io_data[:200]}

    lines.append("")
    lines.append("--- ioData keys (paths) ---")
    for path in sorted(collect_key_paths(io_data)):
        lines.append(f"  {path}")

    lines.append("")
    lines.append("--- ioData (redacted JSON) ---")
    lines.append(json.dumps(redact_structure(io_data), indent=2, ensure_ascii=False))

    lines.append("")
    lines.append("--- firebase header (decoded) ---")
    decoded = decode_firebase_header(firebase_header)
    if isinstance(decoded, dict):
        lines.append(json.dumps(redact_structure(decoded), indent=2, ensure_ascii=False))
    else:
        lines.append(str(decoded))

    auth_related = [
        path
        for path in collect_key_paths(io_data)
        if any(
            token in path.lower()
            for token in ("security", "code", "pin", "number", "usuario", "user", "password")
        )
    ]
    if auth_related:
        lines.append("")
        lines.append("--- paths possibly related to user number / security code ---")
        for path in auth_related:
            lines.append(f"  {path}")

    return "\n".join(lines)
