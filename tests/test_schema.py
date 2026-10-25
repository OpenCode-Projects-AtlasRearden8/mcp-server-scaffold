import pytest

from mcp_server.schema import apply_defaults, check_schema, validate


GOOD = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}


class TestCheckSchema:
    def test_accepts_valid_schema(self):
        assert check_schema(GOOD) == []

    def test_rejects_non_object_schema(self):
        assert check_schema(["string"]) != []

    def test_rejects_unknown_type(self):
        problems = check_schema({"type": "floatpoint"})
        assert any("unknown schema type" in p for p in problems)

    @pytest.mark.parametrize("bad", ["x", 3, None, {}])
    def test_rejects_bad_properties_shape(self, bad):
        problems = check_schema({"type": "object", "properties": bad})
        assert problems

    def test_flags_required_property_not_defined(self):
        problems = check_schema(
            {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["b"]}
        )
        assert any("b" in p for p in problems)

    def test_requires_list_of_strings(self):
        problems = check_schema(
            {"type": "object", "properties": {}, "required": [1, 2]}
        )
        assert any("list of strings" in p for p in problems)

    def test_array_items_recursed(self):
        problems = check_schema(
            {"type": "array", "items": {"type": "banana"}}
        )
        assert any("items" in p for p in problems)


class TestValidate:
    def test_valid_object_passes(self):
        assert validate({"name": "ok"}, GOOD) == []

    def test_missing_required_field(self):
        errors = validate({}, GOOD)
        assert errors == ["name: required field is missing"]

    @pytest.mark.parametrize(
        "value,type_name",
        [
            ("hello", "string"),
            (5, "integer"),
            (5.5, "number"),
            (True, "boolean"),
            (None, "null"),
            ([1], "array"),
            ({}, "object"),
        ],
    )
    def test_type_matches(self, value, type_name):
        schema = {"type": type_name}
        assert validate(value, schema) == []

    @pytest.mark.parametrize(
        "value,type_name",
        [
            (5, "string"),
            ("5", "integer"),
            ("x", "object"),
            ({}, "array"),
            (True, "integer"),
            (5, "boolean"),
        ],
    )
    def test_type_mismatch(self, value, type_name):
        errors = validate(value, {"type": type_name})
        assert len(errors) == 1 and "expected" in errors[0]

    def test_nested_field_validated(self):
        schema = {
            "type": "object",
            "properties": {"a": {"type": "object", "properties": {"b": {"type": "integer"}}}},
        }
        errors = validate({"a": {"b": "nope"}}, schema)
        assert errors == ["a.b: expected integer, got str"]

    def test_additional_properties_false(self):
        schema = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}
        errors = validate({"a": "x", "extra": 1}, schema)
        assert any("unexpected fields: extra" in e for e in errors)

    def test_array_items_and_bounds(self):
        schema = {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 3}
        assert validate([1, 2], schema) == []
        assert any("at least 2" in e for e in validate([1], schema))
        assert any("at most 3" in e for e in validate([1, 2, 3, 4], schema))
        assert validate([1, "two"], schema)

    def test_string_bounds_and_pattern(self):
        schema = {"type": "string", "minLength": 2, "maxLength": 4}
        assert validate("ab", schema) == []
        assert any("minLength" in e for e in validate("a", schema))
        assert any("maxLength" in e for e in validate("abcde", schema))

    def test_pattern_mismatch(self):
        schema = {"type": "string", "pattern": r"^\d+$"}
        assert validate("123", schema) == []
        errors = validate("abc", schema)
        assert any("pattern" in e for e in errors)

    def test_number_bounds(self):
        schema = {"type": "number", "minimum": 1, "maximum": 10}
        assert validate(5, schema) == []
        assert any("minimum" in e for e in validate(0.5, schema))
        assert any("maximum" in e for e in validate(11, schema))

    def test_enum(self):
        schema = {"type": "string", "enum": ["a", "b"]}
        assert validate("a", schema) == []
        assert any("not one of" in e for e in validate("c", schema))


class TestApplyDefaults:
    def test_missing_fields_get_defaults(self):
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "boolean", "default": True},
                "b": {"type": "boolean"},
            },
        }
        assert apply_defaults({}, schema) == {"a": True}
        assert apply_defaults({"a": False}, schema) == {"a": False}

    def test_none_schema_returns_copy(self):
        assert apply_defaults({"x": 1}, {"type": "object"}) == {"x": 1}
