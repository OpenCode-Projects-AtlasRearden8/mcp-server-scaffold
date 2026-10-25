"""Security guards for paths and data handled by tools."""

import os
from pathlib import Path, PureWindowsPath

DEFAULT_MAX_TEXT_BYTES = 1_048_576
DEFAULT_MAX_FILE_BYTES = 5_242_880


class GuardError(ValueError):
    pass


class PathGuard:
    """Restricts all file access to a single root directory."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        allowed_extensions: set[str] | None = None,
        deny_private: bool = True,
    ) -> None:
        self.root = Path(root).resolve(strict=True)
        self.allowed_extensions = {e.lower() for e in (allowed_extensions or ())}
        self.deny_private = deny_private

    def resolve(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative.strip():
            raise GuardError("path must be a non-empty string")
        if "\x00" in relative:
            raise GuardError("path contains a null byte")
        if PureWindowsPath(relative).drive or relative.startswith("\\\\"):
            raise GuardError("windows-style or UNC paths are not allowed")
        candidate = Path(relative)
        if candidate.is_absolute() or candidate.parts and candidate.parts[0] in ("~", ".."):
            raise GuardError(f"path escapes the sandbox root: {relative}")
        resolved = (self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise GuardError(f"path escapes the sandbox root: {relative}")
        if self.deny_private:
            self._check_no_symlinks(self.root / candidate)
        if self.allowed_extensions and resolved.suffix.lower() not in self.allowed_extensions:
            raise GuardError(f"extension {resolved.suffix!r} is not allowed")
        return resolved

    def _check_no_symlinks(self, path: Path) -> None:
        current = self.root
        parts = path.relative_to(self.root).parts
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise GuardError(f"symlink detected in path: {current}")

    def ensure_within_size(self, path: Path, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> None:
        size = path.stat().st_size
        if size > max_bytes:
            raise GuardError(f"{path.name} is {size} bytes, exceeding the {max_bytes} byte limit")

    def readable(self, path: Path, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> Path:
        if not path.exists():
            raise GuardError(f"file does not exist: {path.name}")
        if not path.is_file():
            raise GuardError(f"not a regular file: {path.name}")
        self.ensure_within_size(path, max_bytes=max_bytes)
        return path


def check_text(
    data: str,
    *,
    field: str = "text",
    max_bytes: int = DEFAULT_MAX_TEXT_BYTES,
    allow_control_chars: bool = False,
) -> None:
    """Reject oversized, binary, or otherwise unsafe text before it is written."""
    if not isinstance(data, str):
        raise GuardError(f"{field} must be a string")
    encoded_size = len(data.encode("utf-8"))
    if encoded_size > max_bytes:
        raise GuardError(f"{field} is {encoded_size} bytes, exceeding the {max_bytes} byte limit")
    if "\x00" in data:
        raise GuardError(f"{field} contains a null byte")
    if not allow_control_chars:
        # Allow tab, newline, carriage return; reject other C0 control characters.
        for ch in data:
            if ord(ch) < 32 and ch not in "\t\n\r":
                raise GuardError(f"{field} contains control character U+{ord(ch):04X}")


def safe_stem(name: str, *, fallback: str = "file") -> str:
    """Turn arbitrary input into a safe filename stem."""
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.strip())
    cleaned = cleaned.strip("._") or fallback
    if cleaned in (".", ".."):
        cleaned = fallback
    return cleaned[:80]
