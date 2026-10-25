# STATUS.md

## What was built

**mcp-server-scaffold** — a GitHub template repository for building your own
MCP (Model Context Protocol) server in pure Python stdlib. Built by Asdale
Dynamics, LLC as a beginner-friendly, local-first starting point.

Components:

- `mcp_server/server.py` — complete JSON-RPC 2.0 engine over stdio:
  `initialize` handshake, `notifications/initialized`, `ping`, `tools/list`,
  `tools/call`; correct JSON-RPC error codes (-32700, -32600, -32601, -32602,
  -32603); protocol logic separated into `MCPKernel` so the transport is
  swappable and testable.
- `mcp_server/schema.py` — small typed-schema validator + self-check
  (`check_schema`) covering types, required fields, bounds, patterns, enums,
  array items, `additionalProperties: False`, and defaults-with-apply.
- `mcp_server/guards.py` — `PathGuard` (sandbox to one root, rejects absolute
  paths, `~`, `..`, Windows/UNC drives, symlink escapes, oversized files),
  `check_text` (rejects null bytes/control characters and oversized UTF-8),
  `safe_stem`.
- `mcp_server/safeio.py` — the backup-before-write pattern:
  `backup_before_write` (rolling `.bak` copies, newest-first pruning, never
  fewer than 1, collision-safe names), `BackupDir` (<root>/.backups/<tool>/),
  `write_text_safe` (temp file + atomic `os.replace`, backups the original).
- `mcp_server/tools/` — `base.py` (Tool base class: auto-validated arguments,
  defaults, malformed-schema rejection at class definition) + Registry;
  `echo.py` (example tool #1) and `note_writer.py` (example tool #2 using
  guards + backups).
- `mcp_server/logging_util.py` — request/response JSON logging to **stderr
  only** (the stdio transport stays clean), body truncation, off switch
  (`--no-logging`).
- Tests: `tests/` — 154 offline pytest cases (schema, dispatch, guards,
  safeio/backups, individual tools, end-to-end stdio handshake/concurrency).
- Docs: `README.md` (what's inside, run instructions, 3-step tutorial for a
  first custom tool, publish-checklist), `pyproject.toml`,
  `.gitignore`, MIT `LICENSE`.

## How to run it

```bash
# protocol over stdio (this is what MCP clients execute)
python -m mcp_server --root ./sandbox

# flags: --root FOLDER (sandbox for file tools, default .), --no-logging, --help

# test suite
python -m pytest

# quick manual smoke test (handshake + list + call)
printf '%s\n%s\n%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"clientInfo":{"name":"t","version":"0"}}}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
 '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"echo","arguments":{"message":"hi","shout":true}}}' \
 | python -m mcp_server
```

MCP client config points a client at: `command: python, args: [-m,
mcp_server, --root, /absolute/path]` (README shows a JSON example).

## Verification results

- `python -m pytest` — **154 passed, 0 failed** (offline; also passes inside a
  fresh venv with the package installed in editable mode).
- `python -m mcp_server --help` — prints usage, exits 0, does not start the
  protocol loop.
- `python -m pip install -e .` in a clean venv — succeeds; console script and
  module both importable. (System Python on this machine is PEP 668 managed,
  so a venv was used to verify.)
- Manual end-to-end over a real pipe: initialize → tools/list → tools/call
  (`note_write` created `demo/demo.md`; second call **backed up** the original
  to `.backups/note_write/*.bak` before overwriting; `../escape.md` rejected
  with JSON-RPC error -32602 and created no file outside the sandbox; `echo`
  with `shout: true` → `HOLA`). Logging appeared on stderr only; stdout
  carried exactly one line per JSON-RPC response.
- Guards verified live: Windows drive paths, UNC, `~`, `..`, absolute, null
  bytes, symlink-inside-sandbox, extension allowlist — all rejected.

## Known gaps

- The schema validator covers the common subset (no `oneOf`/`allOf`/deep
  formats). Swap `schema.py` for a full JSON Schema library if needed; the
  Tool interface is unchanged.
- Protocol surface implements the MCP core (initialize/ping/tools/*).
  Resources, prompts, sampling, and server-initiated logging notifications
  are not implemented; extend `MCPKernel._handlers` if you need them.
- Backups are per-directory rolling `.bak` (default 5 kept) — insurance, not
  versioning; no diffing or restore tooling.
- No online/integration test against a real MCP client (Claude Desktop &c.);
  the e2e tests emulate the wire over stdio pipes instead, keeping the suite
  fully offline.
- Example tool #2 intentionally creates missing subfolders on first write.
  If you want a stricter mode, drop the `path.parent.mkdir(...)` line —
  missing folders will surface as errors rather than auto-creation.
