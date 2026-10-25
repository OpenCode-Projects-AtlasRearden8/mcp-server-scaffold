"""Defaults and helpers for building your tool registry."""

from .base import Registry, Tool, ToolError, content_text
from .echo import EchoTool
from .note_writer import NoteWriterTool

__all__ = [
    "Registry",
    "Tool",
    "ToolError",
    "content_text",
    "EchoTool",
    "NoteWriterTool",
    "build_default_registry",
    "register_all",
]


def register_all(registry: Registry, root: str) -> None:
    """Register the example tools. Add your own tools here."""
    registry.register(EchoTool())
    registry.register(NoteWriterTool(root))


def build_default_registry(root: str) -> Registry:
    registry = Registry()
    register_all(registry, root)
    return registry
