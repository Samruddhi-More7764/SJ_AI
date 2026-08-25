import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from vanna.core.llm import LlmMessage, LlmRequest, LlmResponse
from vanna.core.tool import ToolCall, ToolSchema
from vanna.core.user import User

from app.llm import StockJarvisLlmService


def _request(tools=None):
    user = User(id="local", username="stockjarvis", group_memberships=["user"])
    return LlmRequest(
        messages=[LlmMessage(role="user", content="top 10 companies by revenue")],
        user=user,
        tools=tools,
        system_prompt="test",
    )


def test_tools_request_uses_non_streaming_create():
    svc = StockJarvisLlmService(model="test-model", api_key="sk-test", base_url="http://example.invalid/v1")
    message = SimpleNamespace(
        content="I'll fetch the top 10.",
        tool_calls=[
            SimpleNamespace(
                id="t1",
                function=SimpleNamespace(
                    name="run_sql",
                    arguments='{"sql": "SELECT 1"}',
                ),
            )
        ],
    )
    choice = SimpleNamespace(message=message, finish_reason="tool_calls")
    resp = SimpleNamespace(choices=[choice], usage=None)
    svc._client = MagicMock()
    svc._client.chat.completions.create.return_value = resp

    tools = [ToolSchema(name="run_sql", description="sql", parameters={"type": "object"})]
    result = asyncio.run(svc.send_request(_request(tools=tools)))

    kwargs = svc._client.chat.completions.create.call_args.kwargs
    assert kwargs["stream"] is False
    assert result.tool_calls and result.tool_calls[0].name == "run_sql"


@pytest.mark.asyncio
async def test_stream_request_with_tools_emits_tool_calls_without_hanging():
    svc = StockJarvisLlmService(model="test-model", api_key="sk-test", base_url="http://example.invalid/v1")

    async def fake_send(request):
        return LlmResponse(
            content="I'll fetch the top 10.",
            tool_calls=[ToolCall(id="t1", name="run_sql", arguments={"sql": "SELECT 1"})],
            finish_reason="tool_calls",
        )

    svc.send_request = fake_send  # type: ignore[method-assign]
    tools = [ToolSchema(name="run_sql", description="sql", parameters={"type": "object"})]
    chunks = []
    async for chunk in svc.stream_request(_request(tools=tools)):
        chunks.append(chunk)
    assert any(c.content for c in chunks)
    assert any(c.tool_calls for c in chunks)
