"""Normalized-question answer cache (filesystem) plus per-turn debug stash."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

CACHE_DIR = Path("./answer_cache")

_pending: Dict[str, Dict[str, Any]] = {}

VersionFn = Callable[[], Optional[str]]


def normalize_question(question: str) -> str:
    return " ".join((question or "").strip().lower().split())


def cache_key(question: str) -> str:
    return hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()


def sql_hash(sql: str) -> str:
    return hashlib.sha256((sql or "").encode("utf-8")).hexdigest()[:16]


def jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


class AnswerCache:
    """Filesystem backend used by tests. Production uses PostgresAnswerCache."""

    def __init__(
        self,
        directory: Path = CACHE_DIR,
        data_version: Optional[str] = None,
        data_version_fn: Optional[VersionFn] = None,
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.data_version = data_version
        self.data_version_fn = data_version_fn

    def current_version(self) -> Optional[str]:
        if self.data_version_fn is not None:
            return self.data_version_fn()
        return self.data_version

    def get(self, question: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        del session_id
        path = self.directory / f"{cache_key(question)}.json"
        if not path.exists():
            return None
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        current = self.current_version()
        stored = record.get("data_version")
        if current is not None and stored != current:
            path.unlink(missing_ok=True)
            return None
        return record

    def put(
        self,
        question: str,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> None:
        del session_id
        record = {
            **payload,
            "question": question,
            "normalized": normalize_question(question),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "data_version": self.current_version(),
        }
        path = self.directory / f"{cache_key(question)}.json"
        path.write_text(json.dumps(record, default=str, indent=2))


def remember_sql_result(conversation_id: str, **fields: Any) -> None:
    if not conversation_id:
        return
    slot = _pending.setdefault(conversation_id, {})
    slot.update(fields)
    slot["kind"] = "sql"
    sql = slot.get("sql") or ""
    columns = slot.get("columns") or []
    rows = slot.get("rows") or []
    if sql:
        from app.provenance import build_provenance

        slot["provenance"] = build_provenance(sql, columns, rows)


def remember_chart(conversation_id: str, chart: Optional[Dict[str, Any]]) -> None:
    if not conversation_id or chart is None:
        return
    _pending.setdefault(conversation_id, {})["chart"] = chart


def peek_pending(conversation_id: str) -> Optional[Dict[str, Any]]:
    if not conversation_id:
        return None
    return _pending.get(conversation_id)


def take_pending(conversation_id: str) -> Optional[Dict[str, Any]]:
    return _pending.pop(conversation_id, None)
