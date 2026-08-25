"""Claude via AI Credits with timeouts. Never leave a tool-call stream open."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Dict, Optional

from vanna.core.llm import LlmRequest, LlmResponse, LlmStreamChunk
from vanna.integrations.openai import OpenAILlmService

logger = logging.getLogger("stockjarvis")

LLM_TIMEOUT_S = 90.0
DEFAULT_MAX_TOKENS = 4096


class StockJarvisLlmService(OpenAILlmService):
    """OpenAI-compatible client that does not hang on streamed tool calls."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        organization: Optional[str] = None,
        base_url: Optional[str] = None,
        **extra_client_kwargs: Any,
    ) -> None:
        extra_client_kwargs.setdefault("timeout", LLM_TIMEOUT_S)
        super().__init__(
            model=model,
            api_key=api_key,
            organization=organization,
            base_url=base_url,
            **extra_client_kwargs,
        )

    async def send_request(self, request: LlmRequest) -> LlmResponse:
        if request.max_tokens is None:
            request = request.model_copy(update={"max_tokens": DEFAULT_MAX_TOKENS})
        t0 = time.perf_counter()
        logger.info(
            "event=llm_request tools=%s max_tokens=%s",
            bool(request.tools),
            request.max_tokens,
        )
        try:
            return await asyncio.to_thread(self._send_request_blocking, request)
        finally:
            logger.info("event=llm_request_done elapsed_s=%.2f", time.perf_counter() - t0)

    def _send_request_blocking(self, request: LlmRequest) -> LlmResponse:
        payload: Dict[str, Any] = self._build_payload(request)
        resp = self._client.chat.completions.create(**payload, stream=False)
        if not resp.choices:
            return LlmResponse(content=None, tool_calls=None, finish_reason=None)
        choice = resp.choices[0]
        content = getattr(choice.message, "content", None)
        tool_calls = self._extract_tool_calls_from_message(choice.message)
        usage: Dict[str, int] = {}
        if getattr(resp, "usage", None):
            usage = {
                k: int(v)
                for k, v in {
                    "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(resp.usage, "completion_tokens", 0),
                    "total_tokens": getattr(resp.usage, "total_tokens", 0),
                }.items()
                if v is not None
            }
        return LlmResponse(
            content=content,
            tool_calls=tool_calls or None,
            finish_reason=getattr(choice, "finish_reason", None),
            usage=usage or None,
        )

    async def stream_request(
        self, request: LlmRequest
    ) -> AsyncGenerator[LlmStreamChunk, None]:
        # AI Credits streaming often stalls after the preamble while tool JSON
        # is still coming. Complete the call in one shot, then emit chunks.
        response = await self.send_request(request)
        if response.content:
            yield LlmStreamChunk(content=response.content)
        if response.tool_calls:
            yield LlmStreamChunk(
                tool_calls=response.tool_calls,
                finish_reason=response.finish_reason,
            )
        else:
            yield LlmStreamChunk(finish_reason=response.finish_reason or "stop")
