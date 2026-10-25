"""Request/response logging that never contaminates the stdio transport."""

import json
import sys
import threading
import time

_lock = threading.Lock()
_enabled = True

MAX_LOGGED_BODY = 500


def set_logging_enabled(enabled: bool) -> None:
    global _enabled
    _enabled = bool(enabled)


def log_jsonrpc(direction: str, payload: dict, *, to_file=None) -> None:
    """Write a one-line JSONR record to stderr (or a file), with body truncation."""
    if not _enabled:
        return
    record = {"ts": round(time.time(), 3), "dir": direction, "id": payload.get("id")}
    if "method" in payload:
        record["method"] = payload["method"]
    for key in ("result", "error", "params"):
        if key in payload:
            body = json.dumps(payload[key], ensure_ascii=False, default=str)
            if len(body) > MAX_LOGGED_BODY:
                body = body[:MAX_LOGGED_BODY] + f"... (+{len(body) - MAX_LOGGED_BODY} chars)"
            record[key] = body
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        if to_file is not None:
            to_file.write(line + "\n")
        else:
            print(line, file=sys.stderr, flush=True)


def log_event(message: str, *, to_file=None) -> None:
    if not _enabled:
        return
    with _lock:
        if to_file is not None:
            to_file.write(f"{round(time.time(), 3)} EVENT {message}\n")
        else:
            print(f"EVENT {message}", file=sys.stderr, flush=True)
