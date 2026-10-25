import os

import pytest

from mcp_server.safeio import BackupDir, write_text_safe, backup_before_write, _prune_backups


@pytest.fixture()
def path(tmp_path):
    (tmp_path / "notes").mkdir()
    return tmp_path / "notes" / "note.md"


class TestWriteTextSafe:
    def test_creates_new_file(self, path):
        report = write_text_safe(path, "hello")
        assert path.read_text() == "hello"
        assert report.created and report.backup_path is None

    def test_overwrites_existing(self, path, tmp_path):
        path.write_text("v1")
        write_text_safe(path, "v2", backup_dir=tmp_path / "bk")
        assert path.read_text() == "v2"

    def test_backup_created_for_existing_file(self, path, tmp_path):
        path.write_text("v1")
        backup_root = tmp_path / "bk"
        backend = write_text_safe(path, "v2", backup_dir=backup_root)
        assert backend.backup_path is not None
        assert backend.backup_path.read_text() == "v1"
        assert backend.backup_path.name.startswith("note.md.")

    def test_no_backup_for_new_file(self, path, tmp_path):
        report = write_text_safe(path, "first", backup_dir=tmp_path / "bk")
        assert report.backup_path is None

    def test_utf8_multibyte_counting(self, path):
        report = write_text_safe(path, "é" * 3)
        assert report.bytes_written == 6

    def test_report_counts_bytes(self, path):
        report = write_text_safe(path, "abcd")
        assert report.bytes_written == 4


class TestBackupBeforeWrite:
    def test_missing_file_returns_none(self, tmp_path):
        assert backup_before_write(tmp_path / "nope.md", tmp_path / "bk") is None

    def test_backup_preserves_bytes(self, tmp_path):
        src = tmp_path / "f.bin"
        src.write_bytes(bytes(range(256)))
        backup = backup_before_write(src, tmp_path / "bk")
        assert backup.read_bytes() == src.read_bytes()

    def test_duplicate_names_get_counter_suffix(self, tmp_path):
        src = tmp_path / "f.txt"
        src.write_text("v1")
        b1 = backup_before_write(src, tmp_path / "bk")
        src.write_text("v2")
        b2 = backup_before_write(src, tmp_path / "bk")
        assert b1 != b2
        assert b1.exists() and b2.exists()

    def test_prune_keeps_n(self, tmp_path):
        src = tmp_path / "f.txt"
        src.write_text("x")
        bdir = tmp_path / "bk"
        for i in range(8):
            os.utime(src, ns=(i * 1_000_000_000, i * 1_000_000_000))
            backup_before_write(src, bdir, keep=5)
        backups = sorted(bdir.glob("*.bak"))
        assert len(backups) == 5

    def test_prune_always_keeps_newest(self, tmp_path):
        src = tmp_path / "f.txt"
        src.write_text("x")
        bdir = tmp_path / "bk"
        backup_before_write(src, bdir, keep=0)
        assert len(list(bdir.glob("*.bak"))) == 1
        os.utime(src, ns=(2_000_000_000, 2_000_000_000))
        backup_before_write(src, bdir, keep=0)
        backups = sorted(bdir.glob("*.bak"))
        assert len(backups) == 1
        assert backups[0].stat().st_mtime >= backups[0].stat().st_mtime


class TestBackupDir:
    def test_directory_layout(self, tmp_path):
        bdir = BackupDir(tmp_path, "note_write")
        assert str(bdir.directory).endswith(os.path.join(".backups", "note_write"))

    def test_rolling_history(self, tmp_path):
        bdir = BackupDir(tmp_path, "tool")
        src = tmp_path / "f.md"
        src.write_text("v0")
        for i in range(1, 4):
            os.utime(src, ns=(i * 1_100_000_001, i * 1_100_000_001))
            bdir.save(src, when_ns=i * 1_100_000_001)
            src.write_text(f"v{i}")
        assert len(list(bdir.directory.glob("*.bak"))) == 3
        for i in range(4, 9):
            os.utime(src, ns=(i * 1_100_000_001, i * 1_100_000_001))
            bdir.save(src, when_ns=i * 1_100_000_001)
            src.write_text(f"v{i}")
        remaining = sorted(bdir.directory.glob("*.bak"))
        assert len(remaining) == 5

    def test_latest_and_write_integration(self, tmp_path):
        bdir = BackupDir(tmp_path, "tool")
        assert bdir.latest() is None
        src = tmp_path / "f.md"
        src.write_text("original")
        bdir.save(src)
        write_text_safe(src, "replaced", backup_dir=bdir.directory)
        assert bdir.latest() is not None
        assert bdir.latest().read_text() == "original"
        assert src.read_text() == "replaced"

    def test_explicit_when_ns(self, tmp_path):
        bdir = BackupDir(tmp_path, "tool")
        src = tmp_path / "f.md"
        src.write_text("x")
        backup = bdir.save(src, when_ns=42_100_000_000)
        assert "100000000" in backup.name
