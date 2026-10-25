import pytest

from mcp_server.guards import GuardError
from mcp_server.safeio import BackupDir
from mcp_server.tools import EchoTool, NoteWriterTool, ToolError


class TestEchoTool:
    def test_describe_shape(self):
        described = EchoTool().describe()
        assert described["name"] == "echo"
        assert described["description"]
        assert described["inputSchema"]["type"] == "object"

    def test_returns_text_block(self):
        blocks = EchoTool().run({"message": "hello"})
        assert blocks == [{"type": "text", "text": "hello"}]

    def test_shout_uppercases(self):
        blocks = EchoTool().run({"message": "hello", "shout": True})
        assert blocks[0]["text"] == "HELLO"

    def test_defaults_applied(self):
        args = EchoTool().check_arguments({"message": "x"})
        assert args["shout"] is False

    @pytest.mark.parametrize(
        "bad_args",
        [{}, {"message": ""}, {"message": 5}, {"message": "x" * 2001}, {"unexpected": 1}],
    )
    def test_invalid_arguments_planned_by_check(self, bad_args):
        with pytest.raises(ToolError):
            EchoTool().check_arguments(bad_args)


class TestNoteWriterTool:
    @pytest.fixture()
    def root(self, tmp_path):
        return tmp_path

    @pytest.fixture()
    def tool(self, root):
        return NoteWriterTool(str(root))

    def test_creates_new_note(self, tool, root):
        blocks = tool.run({"filename": "notes.md", "content": "line one"})
        assert "created notes.md" in blocks[0]["text"]
        assert (root / "notes.md").read_text() == "line one"

    def test_overwrite_keeps_backup(self, tool, root):
        tool.run({"filename": "notes.md", "content": "v1"})
        blocks = tool.run({"filename": "notes.md", "content": "v2"})
        assert "backup" in blocks[0]["text"] or ".bak" in blocks[0]["text"]
        backups = list((root / ".backups" / "note_write").glob("*.bak"))
        assert len(backups) == 1
        assert backups[0].read_text() == "v1"

    @pytest.mark.parametrize(
        "bad_filename",
        ["../evil.md", "plainname", "file.exe", "with space.md", "C:x.md", "null\x00.md", ""],
    )
    def test_filename_guards(self, tool, bad_filename):
        with pytest.raises((GuardError, ToolError)):
            tool.run({"filename": bad_filename, "content": "x"})

    def test_creates_missing_parent_folders(self, tool, root):
        tool.run({"filename": "sub/dir/notes.md", "content": "x"})
        assert (root / "sub" / "dir" / "notes.md").read_text() == "x"

    def test_content_control_char_rejected(self, tool):
        with pytest.raises((GuardError, ToolError)):
            tool.run({"filename": "n.md", "content": "bad\x02content"})

    def test_append_joins_with_newline(self, tool, root):
        tool.run({"filename": "log.txt", "content": "first"})
        tool.run({"filename": "log.txt", "content": "second", "append": True})
        assert (root / "log.txt").read_text() == "first\nsecond"

    def test_extension_required_even_for_append(self, tool):
        with pytest.raises((GuardError, ToolError)):
            tool.run({"filename": "log", "content": "second", "append": True})

    def test_empty_content_rejected_by_schema(self, tool):
        with pytest.raises(ToolError):
            tool.check_arguments({"filename": "n.md", "content": ""})


class TestBackupDirOnRoot:
    def test_backups_stay_under_root(self, tmp_path):
        tool = NoteWriterTool(str(tmp_path))
        tool.run({"filename": "x.md", "content": "one"})
        tool.run({"filename": "x.md", "content": "two"})
        keep = BackupDir(tmp_path, "note_write")
        assert keep.latest() is not None
        assert keep.latest().parent.parent.parent == tmp_path.resolve()
