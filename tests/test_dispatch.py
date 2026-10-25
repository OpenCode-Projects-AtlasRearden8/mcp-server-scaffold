import json

import pytest

from mcp_server.schema import SchemaError
from mcp_server.server import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    MCPKernel,
    RequestError,
)
from mcp_server.tools import EchoTool, Registry, ToolError, build_default_registry
from mcp_server.tools.base import Tool, content_text
from mcp_server.logging_util import set_logging_enabled


@pytest.fixture()
def registry(tmp_path):
    (tmp_path / "sandbox").mkdir()
    reg = build_default_registry(str(tmp_path / "sandbox"))
    return reg


@pytest.fixture()
def kernel(registry):
    return MCPKernel(registry, logging_enabled=False)


def request(method, *, id_value=1, params=None, **extra):
    message = {"jsonrpc": "2.0", "id": id_value, "method": method}
    if params is not None:
        message["params"] = params
    message.update(extra)
    return message


def init_params(**overrides):
    params = {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "pytest-client", "version": "0.0.1"},
    }
    params.update(overrides)
    return params


class TestRawMessageHandling:
    @pytest.mark.parametrize(
        "raw, expected_code",
        [
            ("{broken json", PARSE_ERROR),
            (42, INVALID_REQUEST),
            ("[]", INVALID_REQUEST),
            ({"jsonrpc": "2.0", "method": "ping", "id": 1}, None),
        ],
    )
    def test_invalid_raw_input(self, kernel, raw, expected_code):
        response = kernel.handle_message(raw)
        if expected_code is None:
            assert response["result"] == {}
        else:
            assert response["error"]["code"] == expected_code

    def test_wrong_jsonrpc_version(self, kernel):
        message = {"jsonrpc": "1.0", "id": 1, "method": "ping"}
        response = kernel.handle_message(message)
        assert response["error"]["code"] == INVALID_REQUEST

    def test_missing_method(self, kernel):
        response = kernel.handle_message({"jsonrpc": "2.0", "id": 1})
        assert response["error"]["code"] == INVALID_REQUEST


class TestHandshake:
    def test_initialize_succeeds(self, kernel):
        response = kernel.handle_message(request("initialize", params=init_params()))
        assert response["result"]["serverInfo"]["name"] == "mcp-server-scaffold"
        assert "tools" in response["result"]["capabilities"]
        assert kernel.initialized

    def test_initialize_requires_client_info(self, kernel):
        response = kernel.handle_message(request("initialize", params={}))
        assert response["error"]["code"] == INVALID_PARAMS
        assert not kernel.initialized

    def test_tools_list_before_initialize_fails(self, kernel):
        response = kernel.handle_message(request("tools/list", params={}))
        assert response["error"]["code"] == INVALID_REQUEST

    def test_tools_list_after_initialize(self, kernel):
        kernel.handle_message(request("initialize", params=init_params()))
        response = kernel.handle_message(request("tools/list", params={}))
        names = [tool["name"] for tool in response["result"]["tools"]]
        assert names == ["echo", "note_write"]
        assert all("inputSchema" in tool for tool in response["result"]["tools"])

    def test_ping_works_without_initialization(self, kernel):
        response = kernel.handle_message(request("ping"))
        assert response["result"] == {}

    def test_unknown_method_yields_error(self, kernel):
        response = kernel.handle_message(request("bogus/method"))
        assert response["error"]["code"] == METHOD_NOT_FOUND


class TestToolCallDispatch:
    def test_call_echo(self, kernel):
        kernel.handle_message(request("initialize", params=init_params()))
        response = kernel.handle_message(
            request(
                "tools/call",
                params={"name": "echo", "arguments": {"message": "yo", "shout": True}},
            )
        )
        assert response["result"]["content"][0]["text"] == "YO"
        assert response["result"]["isError"] is False

    def test_call_unknown_tool(self, kernel):
        kernel.handle_message(request("initialize", params=init_params()))
        response = kernel.handle_message(request("tools/call", params={"name": "ghost"}))
        assert response["error"]["code"] == METHOD_NOT_FOUND

    def test_call_with_bad_arguments(self, kernel):
        kernel.handle_message(request("initialize", params=init_params()))
        response = kernel.handle_message(
            request("tools/call", params={"name": "echo", "arguments": {"wrong": True}})
        )
        assert response["error"]["code"] == INVALID_PARAMS

    def test_call_with_non_object_arguments(self, kernel):
        kernel.handle_message(request("initialize", params=init_params()))
        response = kernel.handle_message(
            request("tools/call", params={"name": "echo", "arguments": [1, 2]})
        )
        assert response["error"]["code"] == INVALID_PARAMS

    def test_call_missing_name(self, kernel):
        kernel.handle_message(request("initialize", params=init_params()))
        response = kernel.handle_message(request("tools/call", params={}))
        assert response["error"]["code"] == INVALID_PARAMS

    def test_null_id_request_treated_as_request(self, kernel):
        response = kernel.handle_message(request("ping", id_value=None))
        assert response["result"] == {}
        assert response["id"] is None

    def test_bad_id_type(self, kernel):
        response = kernel.handle_message(request("ping", id_value=[1]))
        assert response["error"]["code"] == INVALID_REQUEST


class TestNotifications:
    def test_notification_without_id_gets_no_response(self, kernel):
        response = kernel.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert response is None

    def test_unknown_notification_ignored(self, kernel):
        assert kernel.handle_message({"jsonrpc": "2.0", "method": "notifications/whatever"}) is None

    def test_tools_list_notification_no_op_before_init(self, kernel):
        response = kernel.handle_message({"jsonrpc": "2.0", "method": "tools/list"})
        assert response is None

class TestToolBase:
    def test_tool_subclass_with_bad_schema_rejected(self):
        with pytest.raises(TypeError):

            class BrokenTool(Tool):
                name = "broken"
                description = "bad schema"
                input_schema = {"type": "nonsense"}

    def test_content_text_shape(self):
        assert content_text("hi") == {"type": "text", "text": "hi"}


class TestRegistry:
    def test_register_and_lookup(self, tmp_path):
        reg = Registry()
        tool = EchoTool()
        reg.register(tool)
        assert reg.get("echo") is tool
        assert reg.names() == ["echo"]

    def test_duplicate_registration_rejected(self):
        reg = Registry()
        reg.register(EchoTool())
        with pytest.raises(ValueError):
            reg.register(EchoTool())

    def test_unknown_lookup_returns_none(self):
        assert Registry().get("nothing") is None

    def test_descriptors_sorted_listing(self, tmp_path):
        reg = build_default_registry(str(tmp_path))
        assert reg.names() == sorted(reg.names())
