"""Build per-response source metadata from the SQL that actually ran."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence

from pydantic import Field
from vanna.components import SimpleTextComponent, UiComponent
from vanna.core.rich_component import ComponentLifecycle, ComponentType, RichComponent

SQL_PREVIEW_LIMIT = 800
_ARITH_RE = re.compile(r"(?<![\w:])[+\-*/](?!/)")
_SELECT_RE = re.compile(
    r"\bselect\b(?P<body>.*?)\bfrom\b",
    re.IGNORECASE | re.DOTALL,
)

SOURCE_MAPPED = (
    "value_numeric from filings via approved metric mappings"
)
SOURCE_SQL = "computed in SQL from filings value_numeric"


def _unique_strings(rows: Sequence[Dict[str, Any]], *keys: str) -> List[str]:
    seen = []
    found = set()
    for row in rows:
        for key in keys:
            value = row.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if not text or text in found:
                continue
            found.add(text)
            seen.append(text)
    return seen


def _select_list(sql: str) -> str:
    match = _SELECT_RE.search(sql or "")
    if not match:
        return sql or ""
    return match.group("body")


def _sql_has_arithmetic(sql: str) -> bool:
    return bool(_ARITH_RE.search(_select_list(sql)))


def _truncate_sql(sql: str) -> str:
    compact = " ".join((sql or "").split())
    if len(compact) <= SQL_PREVIEW_LIMIT:
        return compact
    return compact[: SQL_PREVIEW_LIMIT - 1] + "…"


def _join(values: Iterable[str], empty: str = "") -> str:
    items = [item for item in values if item]
    return ", ".join(items) if items else empty


def build_provenance(
    sql: str,
    columns: Optional[Sequence[str]] = None,
    rows: Optional[Sequence[Dict[str, Any]]] = None,
    derived_formulas: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    del columns
    row_list = list(rows or [])
    tags = _unique_strings(row_list, "qname")
    metrics = _unique_strings(row_list, "metric_name")
    periods = _unique_strings(row_list, "period_end", "period")
    rounding = _unique_strings(row_list, "rounding_level")
    companies = _unique_strings(row_list, "company_name", "symbol")

    arith = _sql_has_arithmetic(sql or "")
    source = SOURCE_SQL if arith else SOURCE_MAPPED

    formula_parts: List[str] = []
    if arith:
        snippet = " ".join(_select_list(sql or "").split())
        if snippet:
            formula_parts.append(f"SQL expression: {snippet[:240]}")
    formulas = derived_formulas or {}
    for metric in metrics:
        derived = formulas.get(metric)
        if derived:
            formula_parts.append(f"{metric}: {derived}")
    formula = "; ".join(formula_parts) if formula_parts else "(none)"

    return {
        "source": source,
        "formula": formula,
        "tags": tags,
        "metric": _join(metrics) or "",
        "period": _join(periods) or "",
        "rounding": _join(rounding) or "",
        "companies": companies,
        "sql": _truncate_sql(sql or ""),
    }


def fact_ids_from_rows(rows: Sequence[Dict[str, Any]]) -> List[uuid.UUID]:
    ids: List[uuid.UUID] = []
    seen = set()
    for row in rows or []:
        raw = row.get("fact_id")
        if raw is None:
            continue
        try:
            parsed = uuid.UUID(str(raw))
        except (ValueError, TypeError, AttributeError):
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        ids.append(parsed)
    return ids


class ProvenanceComponent(RichComponent):
    """Frontend-only component; type is rewritten to 'provenance' on serialize."""

    type: ComponentType = ComponentType.CARD
    provenance: Dict[str, Any] = Field(default_factory=dict)

    def serialize_for_frontend(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": "provenance",
            "lifecycle": ComponentLifecycle.CREATE.value,
            "data": dict(self.provenance or {}),
            "children": [],
            "timestamp": self.timestamp,
            "visible": True,
            "interactive": False,
        }


def provenance_ui_component(payload: Dict[str, Any]) -> UiComponent:
    return UiComponent(
        rich_component=ProvenanceComponent(provenance=payload),
        simple_component=SimpleTextComponent(text="How these numbers were produced"),
    )
