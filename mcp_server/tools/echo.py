"""Example tool #1: a friendly echo with typed arguments. Use as your template."""

from typing import Any

from ..guards import check_text
from .base import Tool, content_text


class EchoTool(Tool):
    name = "echo"
    description = "Repeats your message back, optionally shouting (uppercase). The simplest example of a working MCP tool."

    input_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "minLength": 1, "maxLength": 2000},
            "shout": {"type": "boolean", "default": False},
        },
        "required": ["message"],
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> list[dict]:
        message = arguments["message"]
        if arguments.get("shout", False):
            message = message.upper()
        check_text(message)
        return [content_text(message)]
