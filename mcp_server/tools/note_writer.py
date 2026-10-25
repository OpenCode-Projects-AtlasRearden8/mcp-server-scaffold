"""Example tool #2: safe file writing with guards and backup-before-write.

This is the pattern to copy for any tool that modifies files on disk.
"""

import re
from typing import Any

from ..guards import GuardError, PathGuard, check_text
from ..schema import apply_defaults
from ..safeio import BackupDir, write_text_safe
from .base import Tool, content_text

_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-.]*(?:/[A-Za-z0-9_\-.]+)*\.(?:md|txt)$")


class NoteWriterTool(Tool):
    name = "note_write"
    description = (
        "Writes a note to a markdown file inside the sandbox folder. "
        "If the file already exists it is backed up first, never overwritten blindly."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "minLength": 1, "maxLength": 120},
            "content": {"type": "string", "minLength": 1, "maxLength": 100_000},
            "append": {"type": "boolean", "default": False},
        },
        "required": ["filename", "content"],
        "additionalProperties": False,
    }

    def __init__(self, root: str) -> None:
        self._guard = PathGuard(root, allowed_extensions={".md", ".txt"})
        self._backups = BackupDir(root=self._guard.root, tool_name=self.name)

    def run(self, arguments: dict[str, Any]) -> list[dict]:
        args = apply_defaults(arguments, self.input_schema)
        filename = args["filename"]
        content = args["content"]
        append = args["append"]

        check_text(content, field="content", max_bytes=100_001)
        if not _FILENAME_PATTERN.fullmatch(filename):
            raise GuardError(
                "filename must use letters, numbers, dots, dashes, underscores, "
                "single forward slashes for folders, and end in .md or .txt"
            )

        path = self._guard.resolve(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        if append and path.exists():
            previous = path.read_text(encoding="utf-8", errors="strict")
            content = previous.rstrip("\n") + "\n" + content

        report = write_text_safe(path, content, backup_dir=self._backups.directory)

        summary = (
            f"created {path.name} ({report.bytes_written} bytes)"
            if report.created
            else f"wrote {path.name} ({report.bytes_written} bytes)"
        )
        if report.backup_path is not None:
            summary += f"; previous version saved to {report.backup_path.relative_to(self._guard.root)}"
        return [content_text(summary)]
