import json
import threading

import pytest

from mcp_server import __version__
from mcp_server.server import StdioTransport, main
from mcp_server.tools import build_default_registry


@pytest.fixture()
def sandbox(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return d


def run_lines(kernel, lines):
    reader = [json.dumps(line) if isinstance(line, dict) else line for line in lines]
    writer = io_writer()
    transport = StdioTransport(kernel, reader=iter(reader), writer=writer)
    transport.serve_forever()
    return writer.getvalue(), transport


def io_writer():
    import io

    return io.StringIO()


def parse_responses(output):
    return [json.loads(line) for line in output.strip().splitlines() if line.strip()]


class TestEndToEndStdio:
    def test_full_handshake_and_call(self, sandbox):
        from mcp_server.server import MCPKernel

        kernel = MCPKernel(build_default_registry(str(sandbox)), logging_enabled=False)
        output, _ = run_lines(
            kernel,
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"clientInfo": {"name": "t", "version": "0"}},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "echo", "arguments": {"message": "done"}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "note_write", "arguments": {"filename": "hello.md", "content": "# Hi"}},
                },
            ],
        )
        responses = parse_responses(output)
        assert [r["id"] for r in responses] == [1, 2, 3, 4]
        assert responses[1]["result"]["tools"][0]["name"] == "echo"
        assert responses[2]["result"]["content"][0]["text"] == "done"
        assert (sandbox / "hello.md").exists()
        assert "# Hi" in (sandbox / "hello.md").read_text()

    def test_blank_lines_are_skipped(self, sandbox):
        from mcp_server.server import MCPKernel

        kernel = MCPKernel(build_default_registry(str(sandbox)), logging_enabled=False)
        output, _ = run_lines(kernel, ["", "   ", '{"jsonrpc": "2.0", "id": 1, "method": "ping"}'])
        responses = parse_responses(output)
        assert len(responses) == 1 and responses[0]["id"] == 1

    def test_transport_flushes_separately(self, sandbox):
        from mcp_server.server import MCPKernel

        kernel = MCPKernel(build_default_registry(str(sandbox)), logging_enabled=False)
        transport = StdioTransport(
            kernel, reader=iter([]), writer=io_writer()
        )
        transport.serve_forever()
        assert transport._writer.getvalue() == ""


class TestLogging:
    def test_logging_never_writes_to_stdout(self, sandbox, capsys):
        from mcp_server.server import MCPKernel

        kernel = MCPKernel(build_default_registry(str(sandbox)), logging_enabled=True)
        run_lines(
            kernel,
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"clientInfo": {"name": "t", "version": "0"}},
                }
            ],
        )
        captured = capsys.readouterr()
        assert captured.out.count("\n") == 0
        assert '"initialize"' in captured.err


class TestMain:
    def test_help_exits_cleanly(self, capsys):
        assert main(["--help"]) == 0
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_missing_root_value(self, capsys):
        code = main(["--root"])
        assert code == 2
        assert "requires a value" in capsys.readouterr().err

    def test_unusable_root(self, capsys, tmp_path):
        blocked = tmp_path / "file.txt"
        blocked.write_text("x")
        code = main(["--root", str(blocked / "under-file")])
        assert code == 2

    def test_server_module_version(self):
        assert __version__


class TestConcurrentWritesSerialized:
    def test_writes_are_newline_delimited_under_threads(self, sandbox):
        from mcp_server.server import MCPKernel

        kernel = MCPKernel(build_default_registry(str(sandbox)), logging_enabled=False)
        transport = StdioTransport(kernel, reader=iter([]), writer=io_writer())
        writer = io_writer()
        threads = []
        for _ in range(4):
            thread = threading.Thread(
                target=lambda: transport._write(writer, {"jsonrpc": "2.0", "id": 1, "result": {}})
            )
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        lines = parse_responses(writer.getvalue())
        assert len(lines) == 4
        assert all(line == {"jsonrpc": "2.0", "id": 1, "result": {}} for line in lines)
