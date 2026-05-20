#!/usr/bin/env python3
"""Export Zentraly flows from a mitmproxy .flow file to JSON lines."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from mitmproxy import io as mitm_io
from mitmproxy.http import HTTPFlow

HOST = "ztprdrestservicesv2.azurewebsites.net"
AUTH_RE = re.compile(r"(ztv2(?:Auth|Token))(.+)", re.IGNORECASE)


def redact_auth(value: str) -> str:
    match = AUTH_RE.match(value)
    if match:
        prefix, rest = match.group(1), match.group(2)
        return f"{prefix}*** (len={len(rest)}, segments={rest.count(':') + 1})"
    return "***"


def flow_to_record(flow: HTTPFlow) -> dict:
    request = flow.request
    record: dict = {
        "method": request.method,
        "url": request.pretty_url,
        "headers": {},
        "request_body": None,
        "status": flow.response.status_code if flow.response else None,
        "response_body": None,
    }
    for key, value in request.headers.items(multi=True):
        if key.lower() == "authorization":
            record["headers"][key] = redact_auth(value)
        elif key.lower() == "firebase":
            record["headers"][key] = value[:80] + "…"
        else:
            record["headers"][key] = value

    if request.content:
        try:
            record["request_body"] = json.loads(request.content)
        except json.JSONDecodeError:
            record["request_body"] = request.content.decode(errors="replace")[:500]

    if flow.response and flow.response.content:
        try:
            record["response_body"] = json.loads(flow.response.content)
        except json.JSONDecodeError:
            record["response_body"] = flow.response.content.decode(errors="replace")[:500]

    return record


def main() -> None:
    flow_path = Path(sys.argv[1] if len(sys.argv) > 1 else "")
    if not flow_path.is_file():
        print("Usage: export-flows.py path/to/file.flow", file=sys.stderr)
        sys.exit(1)

    with flow_path.open("rb") as handle:
        reader = mitm_io.FlowReader(handle)
        for flow in reader.stream():
            if not isinstance(flow, HTTPFlow):
                continue
            if HOST not in (flow.request.host or ""):
                continue
            print(json.dumps(flow_to_record(flow), ensure_ascii=False))


if __name__ == "__main__":
    main()
