# mcp-server-scaffold

A GitHub template repository for building your **own MCP server** in pure
Python — no third-party packages, no API keys, no magic.

Built by **Asdale Dynamics, LLC** as a beginner-friendly starting point for
Dylan Asdale's readers: clear, warm, polished, tested, and local-first.

The MCP (Model Context Protocol) is how AI agents like Claude call the tools
you write. This scaffold handles the boring, fiddly parts *for* you, so you can
focus on your tool's actual job.

## What's inside

```
mcp_server/
  __main__.py        python -m mcp_server entry point
  server.py          JSON-RPC 2.0 over stdio: the whole protocol engine
  schema.py          small JSON-schema validator (types, bounds, enums, defaults)
  guards.py          path sandbox + data guards (no escapes, no binary junk)
  safeio.py          backup-before-write helpers, so tools never destroy data
  tools/             your tools live here (two examples included)
    base.py          Tool base class + registry
    echo.py          example #1: the simplest working tool
    note_writer.py   example #2: guarded file writing with automatic backups
tests/               offline pytest suite: schema, dispatch, guards, e2e stdio
```

- **Zero runtime dependencies.** Only the Python 3.10+ standard library.
- **Safe by default.** Every file tool is sandboxed to one folder, rejects
  symlink escapes and control characters, and backs up files before overwriting.
- **Logged but clean.** Request/response logging goes to *stderr* only, so the
  stdio transport never gets polluted.
- **Tested offline.** ~100 pytest cases covering schema validation, dispatch,
  guards, backups, and a full end-to-end stdio handshake.

## Run it

```bash
# run the server (it speaks JSON-RPC on stdin/stdout)
python -m mcp_server --root ./sandbox

# run the test suite
python -m pytest
```

`--root` is the folder your file tools may touch (default: `.`).
`--no-logging` silences the stderr diagnostics.

## Tutorial: your first custom tool in 3 steps

### Step 1 — Write the tool

Create `mcp_server/tools/word_count.py`:

```python
from typing import Any

from .base import Tool, content_text


class WordCountTool(Tool):
    name = "word_count"
    description = "Counts words, characters, and lines in a piece of text."

    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1, "maxLength": 100_000},
        },
        "required": ["text"],
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> list[dict]:
        text = arguments["text"]
        words = len(text.split())
        chars = len(text)
        lines = text.count("\n") + 1
        summary = f"{words} words, {chars} characters, {lines} line(s)"
        return [content_text(summary)]
```

What just happened:

- `input_schema` is the *typed contract* the AI sees. It declares that one
  argument exists, that it is a string, and how long it may be. The base class
  validates incoming arguments against it automatically — bad arguments never
  reach your `run()`, and the class refuses to even load if the schema itself
  is malformed.
- `run()` receives pre-validated arguments and returns MCP *content blocks*.
  Plain text blocks are the common case; the AI reads your text back.
- No comments needed, no boilerplate: one schema, one method.

### Step 2 — Register it

Open `mcp_server/tools/__init__.py` and add two lines to `register_all`:

```python
from .word_count import WordCountTool
...
registry.register(WordCountTool())
```

Order matters only for how tools appear in listings; the registry rejects
duplicate names for you.

### Step 3 — Test it like a real client

Add `tests/test_word_count.py`:

```python
from mcp_server.tools import build_default_registry
from mcp_server.tools.word_count import WordCountTool


def test_counts_words():
    tool = WordCountTool()
    assert tool.run({"text": "one two three"})[0]["text"] == "3 words, 13 characters, 1 line(s)"


def test_registry_exposes_it():
    reg = build_default_registry(".")
    assert "word_count" in reg.names()
```

Run `python -m pytest` — that's the whole loop. Handshake, dispatch, schema
validation, and logging are already wired: your tool is now callable by any MCP
client.

### Want to touch files? Copy the pattern instead of the habit

Look at `mcp_server/tools/note_writer.py` — that is the template for any
file-modifying tool:

1. Wrap a folder in `PathGuard(...)` so users can't read/write outside it.
2. Run `check_text(...)` on anything headed for disk.
3. Write with `write_text_safe(...)`, which saves a rolling `.bak` backup
   before overwriting and writes through a temp file, so a crash mid-write
   never corrupts or deletes your data — lessons learned, baked in.

## Publishing your server: checklist

Before you share the repo or point a client at it:

- [ ] `python -m pytest` passes from a clean clone.
- [ ] `python -m mcp_server --help` prints usage without starting the protocol.
- [ ] Your tools have names, descriptions, and tight schemas (min/max lengths,
      required fields, `additionalProperties: False`).
- [ ] File-enabled tools are rooted with `PathGuard` and use `write_text_safe`.
- [ ] No absolute personal paths, no secrets, no API keys anywhere — including
      tests and README examples.
- [ ] `LICENSE` kept as MIT with your copyright line; README credits updated.
- [ ] README quickstart (this file's sections) still matches your tools.
- [ ] Tested with a real client: connect over stdio, list tools, call one.
- [ ] Sanity-checked in a fresh directory: `--root` folder auto-created,
      backups land in `sandbox/.backups/<tool>/`.
- [ ] Version bumped in `pyproject.toml` and `mcp_server/__init__.py`.

## How clients connect

Most MCP clients run your server as a subprocess and talk JSON-RPC over stdio.
A typical client config looks like:

```json
{
  "mcpServers": {
    "my-scaffold": {
      "command": "python",
      "args": ["-m", "mcp_server", "--root", "/absolute/path/to/sandbox"]
    }
  }
}
```

Run from your repo folder so `python -m mcp_server` resolves the package.

## Notes and limits (be honest with yourself)

- The schema validator is intentionally small: types, required fields, bounds,
  enums, patterns, defaults. It covers the great majority of beginner tools.
  If you need full JSON Schema, swap `schema.py` for any library — the tool
  interface stays the same.
- Backups land beside the data (`<root>/.backups/<tool>/`) and keep the 5 most
  recent versions per directory. They're insurance, not sync.
- This scaffold implements the core of the MCP protocol (initialize, ping,
  tools/list, tools/call). Resources and prompts/draft-primitives are out of
  scope; the `MCPKernel` class is deliberately small so you can extend it.

## License

MIT — Copyright (c) 2026 Asdale Dynamics, LLC.
From *The Massive AI Manual* tradition: plain English, step by step, never
assuming you were born knowing this. See https://dylanasdale.github.io.
