import os

import pytest

from mcp_server.guards import (
    GuardError,
    PathGuard,
    check_text,
    safe_stem,
)


@pytest.fixture()
def guard(tmp_path):
    return PathGuard(tmp_path)


class TestPathGuardResolve:
    def test_resolves_inside_root(self, guard, tmp_path):
        resolved = guard.resolve("notes/todo.md")
        assert str(resolved).startswith(str(tmp_path))
        assert resolved.name == "todo.md"

    def test_nested_relative_ok(self, guard):
        resolved = guard.resolve("a/b/c.txt")
        assert "a" in resolved.parts

    @pytest.mark.parametrize(
        "bad",
        [
            "../escape.md",
            "../../etc/passwd",
            "~/.ssh/id_rsa",
            "~/x",
            "/absolute/path.txt",
            "C:/Windows/win.ini",
            "C:\\Windows\\win.ini",
            "\\\\server\\share\\file",
            "",
            "   ",
            "null\x00byte.txt",
        ],
    )
    def test_rejects_escapes_and_bad_input(self, guard, bad):
        with pytest.raises(GuardError):
            guard.resolve(bad)

    def test_sneaky_double_dot_segment(self, guard):
        with pytest.raises(GuardError):
            guard.resolve("ok/../../away.txt")

    def test_symlink_escape_denied(self, guard, tmp_path):
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")
        inner_dir = tmp_path / "sandboxfiles"
        inner_dir.mkdir()
        (inner_dir / "link.txt").symlink_to(outside)
        with pytest.raises(GuardError):
            guard.resolve("sandboxfiles/link.txt")

    def test_symlink_to_internal_target_still_denied(self, guard, tmp_path):
        inner_dir = tmp_path / "sandboxfiles"
        inner_dir.mkdir()
        (inner_dir / "real.txt").write_text("ok")
        (inner_dir / "link.txt").symlink_to(inner_dir / "real.txt")
        with pytest.raises(GuardError):
            guard.resolve("sandboxfiles/link.txt")

    def test_symlink_deep_in_chain_denied(self, guard, tmp_path):
        outside = tmp_path / "outside2.txt"
        outside.write_text("b")
        (tmp_path / "llink").symlink_to(outside.parent)
        with pytest.raises(GuardError):
            guard.resolve("llink/file.txt")

    def test_allowed_extensions(self, tmp_path):
        strict = PathGuard(tmp_path, allowed_extensions={".md", ".txt"})
        assert strict.resolve("notes/todo.md")
        with pytest.raises(GuardError):
            strict.resolve("script.exe")

    def test_extension_check_case_insensitive(self, tmp_path):
        strict = PathGuard(tmp_path, allowed_extensions={".md"})
        assert strict.resolve("notes/TODO.MD")


class TestPathGuardFiles:
    def test_readable_missing_file(self, guard, tmp_path):
        with pytest.raises(GuardError):
            guard.readable(tmp_path / "missing.md")

    def test_readable_directory_rejected(self, guard, tmp_path):
        (tmp_path / "adir").mkdir()
        with pytest.raises(GuardError):
            guard.readable(tmp_path / "adir")

    def test_readable_oversize_rejected(self, guard, tmp_path):
        big = tmp_path / "big.txt"
        big.write_bytes(b"x" * 100)
        with pytest.raises(GuardError):
            guard.readable(big, max_bytes=10)

    def test_readable_ok(self, guard, tmp_path):
        f = tmp_path / "ok.txt"
        f.write_text("hi")
        assert guard.readable(f).exists()

    def test_within_size(self, guard, tmp_path):
        f = tmp_path / "s.txt"
        f.write_bytes(b"12345")
        guard.ensure_within_size(f, max_bytes=100)
        with pytest.raises(GuardError):
            guard.ensure_within_size(f, max_bytes=2)


class TestCheckText:
    def test_plain_text_passes(self):
        assert check_text("hello\nworld\t!\r\n") is None

    def test_rejects_null_byte(self):
        with pytest.raises(GuardError):
            check_text("hello\x00world")

    @pytest.mark.parametrize("bad", ["a\x01b", "a\x07b", "a\x1fb"])
    def test_rejects_control_chars(self, bad):
        with pytest.raises(GuardError):
            check_text(bad)

    def test_allows_valid_control_chars(self):
        assert check_text("\t\n\r") is None

    def test_rejects_oversize(self):
        with pytest.raises(GuardError):
            check_text("x" * 50, max_bytes=49)

    def test_uses_utf8_size_not_char_count(self):
        assert check_text("é" * 20, max_bytes=40) is None
        with pytest.raises(GuardError):
            check_text("é" * 20, max_bytes=39)

    def test_rejects_non_string(self):
        with pytest.raises(GuardError):
            check_text(b"bytes")

    def test_custom_field_name_in_error(self):
        with pytest.raises(GuardError) as exc_info:
            check_text("a\x02", field="myfield")
        assert "myfield" in str(exc_info.value)

    def test_control_chars_allowed_when_requested(self):
        assert check_text("a\x02b", allow_control_chars=True) is None


class TestSafeStem:
    def test_alnum_kept(self):
        assert safe_stem("Report-2026_v2") == "Report-2026_v2"

    def test_spaces_become_underscores(self):
        assert safe_stem("my notes") == "my_notes"

    @pytest.mark.parametrize(
        ("dirty", "expected"),
        [
            ("", "file"),
            ("../..", "file"),
            ("///", "file"),
            (".", "file"),
            ("*", "file"),
        ],
    )
    def test_fallbacks(self, dirty, expected):
        assert safe_stem(dirty) == expected

    def test_long_names_truncated(self):
        assert len(safe_stem("x" * 500)) <= 80

    def test_dangerous_chars_replaced(self):
        stem = safe_stem("../con fïg|/pass*")
        assert all(c.isalnum() or c in "-_" for c in stem)
        assert not (os.sep in stem)
