"""Backup-before-write file helpers, so tools never destroy data on failure."""

import os
import tempfile
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WriteReport:
    path: Path
    bytes_written: int
    backup_path: Path | None
    created: bool


class BackupDir:
    """Rolling time-stamped backups kept under <root>/.backups/<tool>/ ."""

    def __init__(self, root: Path, tool_name: str, keep: int = 5) -> None:
        self._dir = root / ".backups" / tool_name
        self._keep = max(int(keep), 1)
        self._history: deque[Path] = deque()
        self._loaded = False

    @property
    def directory(self) -> Path:
        return self._dir

    def _load_history(self) -> None:
        if self._loaded:
            return
        if self._dir.exists():
            backups = sorted(self._dir.glob("*.bak"), key=lambda p: p.stat().st_mtime)
            for backup in backups[-self._keep:]:
                self._history.append(backup)
        self._loaded = True

    def save(self, source: Path, *, when_ns: int | None = None) -> Path:
        self._load_history()
        self._dir.mkdir(parents=True, exist_ok=True)
        stamp = (when_ns if when_ns is not None else source.stat().st_mtime_ns) % 1_000_000_000
        backup = self._dir / f"{source.name}.{stamp}.bak"
        counter = 1
        while backup.exists():
            backup = self._dir / f"{source.name}.{stamp}-{counter}.bak"
            counter += 1
        backup.write_bytes(source.read_bytes())
        self._history.append(backup)
        while len(self._history) > self._keep:
            oldest = self._history.popleft()
            if oldest.exists():
                oldest.unlink()
        return backup

    def latest(self) -> Path | None:
        self._load_history()
        return self._history[-1] if self._history else None


def backup_before_write(path: Path, backup_dir: Path, keep: int = 5) -> Path | None:
    """Copy an existing file into backup_dir before it gets overwritten."""
    if not path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = path.stat().st_mtime_ns
    backup = backup_dir / f"{path.name}.{stamp % 1_000_000_000}.bak"
    counter = 1
    while backup.exists():
        backup = backup_dir / f"{path.name}.{stamp % 1_000_000_000}-{counter}.bak"
        counter += 1
    backup.write_bytes(path.read_bytes())
    _prune_backups(backup_dir, max(keep, 1))
    return backup


def _prune_backups(backup_dir: Path, keep: int) -> None:
    backups = sorted(backup_dir.glob("*.bak"), key=lambda p: p.stat().st_mtime)
    for stale in backups[:-keep]:
        stale.unlink()


def write_text_safe(
    path: Path,
    text: str,
    *,
    backup_dir: Path | None = None,
    keep_backups: int = 5,
) -> WriteReport:
    """Write text atomically: temp file first, backup the original, then replace."""
    created = not path.exists()
    if path.exists() and not path.is_file():
        raise IsADirectoryError(str(path))
    backup_path = None
    if backup_dir is not None and not created:
        backup_path = backup_before_write(path, backup_dir, keep=keep_backups)
    fd, tmp = tempfile.mkstemp(dir=path.parent or Path("."), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return WriteReport(path=path, bytes_written=len(text.encode("utf-8")), backup_path=backup_path, created=created)
