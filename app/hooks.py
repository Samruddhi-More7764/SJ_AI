"""Inject same-thread slots into the system prompt; write the answer cache after a turn."""

from __future__ import annotations

from typing import Any, Optional

from vanna.core.enhancer.base import LlmContextEnhancer
from vanna.core.lifecycle import LifecycleHook
from vanna.core.user import User

from app.cache import AnswerCache, take_pending
from app.provenance import build_provenance
from app.sql_guard import FALLBACK_MESSAGE


class SlotContextEnhancer(LlmContextEnhancer):
    async def enhance_system_prompt(
        self, system_prompt: str, user_message: str, user: User
    ) -> str:
        line = (user.metadata or {}).get("slot_line")
        if not line:
            return system_prompt
        return f"{system_prompt}\n\n{line}"


class CacheWriteHook(LifecycleHook):
    def __init__(self, cache: AnswerCache) -> None:
        self.cache = cache

    def _formulas(self) -> dict:
        getter = getattr(self.cache, "derived_formulas", None)
        if not callable(getter):
            return {}
        try:
            return getter() or {}
        except Exception:
            return {}

    async def after_message(self, result: Any) -> None:
        conversation = result
        conversation_id = getattr(conversation, "id", None)
        if not conversation_id:
            return
        pending = take_pending(conversation_id)
        if not pending:
            return
        messages = getattr(conversation, "messages", None) or []
        user_text = None
        assistant_text = None
        for msg in reversed(messages):
            if assistant_text is None and getattr(msg, "role", None) == "assistant" and getattr(msg, "content", None):
                assistant_text = msg.content
            if user_text is None and getattr(msg, "role", None) == "user" and getattr(msg, "content", None):
                user_text = msg.content
            if user_text and assistant_text:
                break
        if not user_text or not assistant_text:
            return
        if FALLBACK_MESSAGE in assistant_text:
            return
        if pending.get("row_count") in (0, None):
            return
        sql = pending.get("sql") or ""
        columns = pending.get("columns") or []
        rows = pending.get("rows") or []
        formulas = self._formulas()
        provenance = pending.get("provenance")
        if formulas or not provenance:
            provenance = build_provenance(
                sql, columns, rows, derived_formulas=formulas
            )
        self.cache.put(
            user_text,
            {
                "sql": sql,
                "row_count": pending.get("row_count"),
                "columns": columns,
                "rows": rows,
                "chart": pending.get("chart"),
                "markdown": assistant_text,
                "provenance": provenance,
            },
            session_id=conversation_id,
        )
