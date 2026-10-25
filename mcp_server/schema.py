"""A small JSON-schema validator covering the subset MCP tools need."""

from typing import Any


class SchemaError(ValueError):
    pass


_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def check_schema(schema: Any) -> list[str]:
    """Validate the schema definition itself; returns a list of problems."""
    problems: list[str] = []
    if not isinstance(schema, dict):
        return ["schema must be an object"]
    stype = schema.get("type")
    if stype not in _TYPE_CHECKS:
        problems.append(f"unknown schema type: {stype!r}")
    props = schema.get("properties")
    if stype == "object":
        if not isinstance(props, dict) or not props:
            problems.append("object schemas must declare non-empty properties")
        else:
            for name, subschema in props.items():
                if not isinstance(subschema, dict):
                    problems.append(f"property {name!r}: must be an object")
                elif not checker_valid(subschema):
                    problems.append(f"property {name!r}: missing or unknown 'type'")
                for problem in check_schema(subschema):
                    problems.append(f"property {name!r}: {problem}")
    elif props is not None and not isinstance(props, dict):
        problems.append("properties must be an object")
    required = schema.get("required")
    if required is not None:
        if not isinstance(required, list) or not all(
            isinstance(item, str) for item in required
        ):
            problems.append("required must be a list of strings")
        elif props is not None:
            for item in required:
                if item not in props:
                    problems.append(f"required field {item!r} is not defined in properties")
    if stype == "array" and "items" in schema:
        for problem in check_schema(schema["items"]):
            problems.append(f"items: {problem}")
    for key in ("enum", "const", "default"):
        if key in schema and props is not None and key == "enum":
            if not isinstance(schema[key], list) or not schema[key]:
                problems.append(f"{key} must be a non-empty list")
    return problems


def checker_valid(subschema: dict) -> bool:
    return subschema.get("type") in _TYPE_CHECKS


def _path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def validate(instance: Any, schema: Any, prefix: str = "") -> list[str]:
    """Validate an instance against the schema; returns a list of error strings."""
    stype = schema.get("type")
    checker = _TYPE_CHECKS.get(stype)
    if checker and not checker(instance):
        return [f"{prefix or 'value'}: expected {stype}, got {type(instance).__name__}"]

    errors: list[str] = []
    if stype == "object" and isinstance(instance, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{_path(prefix, name)}: required field is missing")
        extra_keys = [k for k in instance if k not in props] if props else []
        allow_extra = schema.get("additionalProperties", True)
        if extra_keys and allow_extra is False:
            errors.append(f"{prefix or 'value'}: unexpected fields: {', '.join(extra_keys)}")
        for name, subschema in props.items():
            if name in instance:
                errors.extend(validate(instance[name], subschema, _path(prefix, name)))
    elif stype == "array" and isinstance(instance, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(instance):
                errors.extend(validate(item, items_schema, f"{prefix}[{i}]" if prefix else f"[{i}]"))
        minimum = schema.get("minItems")
        if minimum is not None and len(instance) < minimum:
            errors.append(f"{prefix or 'value'}: expected at least {minimum} items")
        maximum = schema.get("maxItems")
        if maximum is not None and len(instance) > maximum:
            errors.append(f"{prefix or 'value'}: expected at most {maximum} items")
    elif stype == "string" and isinstance(instance, str):
        minimum = schema.get("minLength")
        if minimum is not None and len(instance) < minimum:
            errors.append(f"{prefix or 'value'}: shorter than minLength {minimum}")
        maximum = schema.get("maxLength")
        if maximum is not None and len(instance) > maximum:
            errors.append(f"{prefix or 'value'}: longer than maxLength {maximum}")
        pattern = schema.get("pattern")
        if pattern is not None:
            import re

            try:
                compiled = re.compile(pattern)
            except re.error as exc:
                errors.append(f"{prefix or 'value'}: invalid pattern ({exc})")
            else:
                if not compiled.search(instance):
                    errors.append(f"{prefix or 'value'}: does not match pattern {pattern!r}")
    elif stype in ("integer", "number") and isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            errors.append(f"{prefix or 'value'}: below minimum {minimum}")
        maximum = schema.get("maximum")
        if maximum is not None and instance > maximum:
            errors.append(f"{prefix or 'value'}: above maximum {maximum}")

    if "enum" in schema and not errors and not isinstance(instance, (dict, list)):
        if instance not in schema["enum"]:
            errors.append(f"{prefix or 'value'}: not one of {schema['enum']!r}")

    return errors


def apply_defaults(instance: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of instance with schema defaults filled in for missing keys."""
    result = dict(instance)
    for name, subschema in schema.get("properties", {}).items():
        if name not in result and "default" in subschema:
            result[name] = subschema["default"]
    return result
