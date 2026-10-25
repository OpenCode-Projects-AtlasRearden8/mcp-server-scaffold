"""A minimal but complete MCP server speaking JSON-RPC 2.0 over stdio.

No third-party dependencies: everything here is the Python stdlib, so the
scaffold runs anywhere Python 3.10+ runs.
"""

import json
import os
import sys
import threading
from typing import Any

from . import __version__
from .guards import GuardError
from .logging_util import log_event, log_jsonrpc
from .schema import SchemaError
from .tools import Registry, ToolError, content_text, register_all

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "mcp-server-scaffold",
    "version": __version__,
    "title": "MCP Server Scaffold (stdlib)",
}

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class RequestError(Exception):
    """Raise this inside a handler to return a controlled JSON-RPC error."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class MCPKernel:
    """Protocol logic separated from the transport, for easy testing."""

    def __init__(self, registry: Registry, *, logging_enabled: bool = True) -> None:
        self.registry = registry
        self.initialized = False
        self.logging_enabled = logging_enabled

    def handle_message(self, message: Any) -> dict | None:
        """Process one decoded JSON-RPC message; None means 'no response'."""
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError as exc:
                return self._error(None, PARSE_ERROR, f"parse error: {exc.msg}")
        if not isinstance(message, dict):
            return self._error(None, INVALID_REQUEST, "message must be an object")
        if message.get("jsonrpc") != JSONRPC_VERSION:
            return self._error(message.get("id"), INVALID_REQUEST, "jsonrpc must be '2.0'")
        method = message.get("method")
        if not isinstance(method, str) or not method:
            return self._error(message.get("id"), INVALID_REQUEST, "missing method")

        is_request = "id" in message
        if is_request and not (
            message.get("id") is None
            or isinstance(message.get("id"), (str, int))
            and not isinstance(message.get("id"), bool)
        ):
            return self._error(None, INVALID_REQUEST, "id must be a string, integer, or null")

        params = message.get("params", {})
        if not isinstance(params, (dict, list)):
            return self._error(message.get("id"), INVALID_REQUEST, "params must be an object or array")

        if self.logging_enabled:
            log_jsonrpc("->" if is_request else "=>", message)

        handler = self._handlers().get(method)
        if handler is None:
            if is_request:
                return self._error(message["id"], METHOD_NOT_FOUND, f"unknown method: {method}")
            return None

        try:
            result = handler(params)
        except RequestError as exc:
            if is_request:
                return self._error(message["id"], exc.code, exc.message, exc.data)
            log_event(f"notification {method} failed: {exc.message}")
            return None
        except (ToolError, SchemaError) as exc:
            if is_request:
                return self._error(message["id"], INVALID_PARAMS, str(exc))
            return None
        except NotInitialized as exc:
            if is_request:
                return self._error(message["id"], INVALID_REQUEST, str(exc))
            return None
        except Exception as exc:
            if is_request:
                return self._error(message["id"], INTERNAL_ERROR, f"internal error: {exc}")
            log_event(f"notification {method} raised: {exc}")
            return None

        if not is_request:
            return None
        response = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        if self.logging_enabled:
            log_jsonrpc("<-", response)
        return response

    def _handlers(self) -> dict:
        return {
            "initialize": self._initialize,
            "notifications/initialized": self._note_initialized,
            "ping": self._ping,
            "tools/list": self._tools_list,
            "tools/call": self._tools_call,
        }

    def _initialize(self, params: dict) -> dict:
        client_info = params.get("clientInfo")
        protocol_version = params.get("protocolVersion", PROTOCOL_VERSION)
        if not isinstance(client_info, dict) or "name" not in client_info:
            raise RequestError(INVALID_PARAMS, "clientInfo.name is required")
        self.initialized = True
        return {
            "protocolVersion": protocol_version,
            "capabilities": {"tools": {"listChanged": False}, "logging": {}},
            "serverInfo": SERVER_INFO,
        }

    def _note_initialized(self, params: dict) -> None:
        log_event("client completed initialization")

    def _ping(self, params: dict) -> dict:
        return {}

    def _tools_list(self, params: dict) -> dict:
        self._require_initialized()
        return {"tools": self.registry.descriptors()}

    def _tools_call(self, params: dict) -> dict:
        self._require_initialized()
        if not isinstance(params, dict):
            raise RequestError(INVALID_PARAMS, "params must be an object")
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str):
            raise RequestError(INVALID_PARAMS, "'name' must be a string")
        tool = self.registry.get(name)
        if tool is None:
            raise RequestError(METHOD_NOT_FOUND, f"unknown tool: {name}")
        try:
            args = tool.check_arguments(arguments)
        except ToolError as exc:
            raise RequestError(INVALID_PARAMS, str(exc)) from exc
        try:
            blocks = tool.run(args)
        except (GuardError, ToolError, SchemaError) as exc:
            raise RequestError(INVALID_PARAMS, str(exc)) from exc
        if not isinstance(blocks, list) or not all(isinstance(b, dict) for b in blocks):
            raise RequestError(INTERNAL_ERROR, f"tool {name} returned malformed content")
        return {"content": blocks, "isError": False}

    def _require_initialized(self) -> None:
        if not self.initialized:
            raise NotInitialized("client must send 'initialize' before using tools")

    @staticmethod
    def _error(id_value: Any, code: int, message: str, data: Any = None) -> dict:
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": id_value, "error": error}


class NotInitialized(Exception):
    pass


class StdioTransport:
    """Reads newline-delimited JSON from stdin, writes one-line responses."""

    def __init__(self, kernel: MCPKernel, *, reader=None, writer=None) -> None:
        self.kernel = kernel
        self._reader = reader
        self._writer = writer
        self._write_lock = threading.Lock()

    def serve_forever(self) -> int:
        reader = self._reader or sys.stdin
        writer = self._writer or sys.stdout
        for raw_line in reader:
            line = raw_line.strip()
            if not line:
                continue
            response = self.kernel.handle_message(line)
            if response is not None:
                self._write(writer, response)
        return 0

    def _write(self, writer, response: dict) -> None:
        line = json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._write_lock:
            writer.write(line)
            writer.flush()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        print("Usage: python -m mcp_server [--root FOLDER] [--no-logging]")
        return 0
    no_logging = "--no-logging" in argv
    root = "."
    if "--root" in argv:
        index = argv.index("--root")
        if index + 1 >= len(argv):
            print("error: --root requires a value", file=sys.stderr)
            return 2
        root = argv[index + 1]
    try:
        os.makedirs(root, exist_ok=True)
        registry = Registry()
        register_all(registry, root)
    except OSError as exc:
        print(f"error: sandbox root unusable: {exc}", file=sys.stderr)
        return 2
    kernel = MCPKernel(registry, logging_enabled=not no_logging)
    transport = StdioTransport(kernel)
    return transport.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
