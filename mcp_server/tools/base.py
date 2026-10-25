"""Tool base class and registry used by the scaffold server."""

from abc import ABC, abstractmethod
from typing import Any

from ..schema import apply_defaults, check_schema, validate


class ToolError(RuntimeError):
    pass


def content_text(text: str) -> dict:
    return {"type": "text", "text": text}


class Tool(ABC):
    name: str = "tool"
    description: str = ""
    input_schema: dict = {"type": "object", "properties": {}}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        problems = check_schema(getattr(cls, "input_schema", {}))
        if problems:
            raise TypeError(f"tool {cls.__name__!r} has an invalid input_schema: {problems}")

    def describe(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    def check_arguments(self, arguments: Any) -> dict:
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ToolError("arguments must be an object")
        arguments = apply_defaults(arguments, self.input_schema)
        errors = validate(arguments, self.input_schema)
        if errors:
            raise ToolError("invalid arguments: " + "; ".join(errors))
        return arguments

    @abstractmethod
    def run(self, arguments: dict[str, Any]) -> list[dict]:
        """Execute the tool and return MCP content blocks."""


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name or not isinstance(tool.name, str):
            raise ValueError("tool name must be a non-empty string")
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def descriptors(self) -> list[dict]:
        return [tool.describe() for tool in self._tools.values()]
