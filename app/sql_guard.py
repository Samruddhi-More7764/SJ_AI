"""Pure SQL allow-list. No database or Vanna imports."""

from __future__ import annotations

import re

import sqlparse

FALLBACK_MESSAGE = "This information is not with us."

_ALLOWED = {"SELECT", "WITH"}

ALLOWED_TABLES = frozenset(
    {
        "companies",
        "filings",
        "financial_facts",
        "tag_catalog",
        "metric_tag_mappings",
        "xbrl_contexts",
        "derived_metric_definitions",
    }
)

_CTE_NAME = re.compile(r"([A-Za-z_][\w]*)\s+AS\s*\(", re.IGNORECASE)
_FROM_JOIN = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:ONLY\s+)?(?:[A-Za-z_][\w]*\.)?([A-Za-z_][\w]*)",
    re.IGNORECASE,
)


def is_read_only_sql(sql: str) -> bool:
    """True only for a single SELECT or WITH statement."""
    if not sql or not sql.strip():
        return False

    statements = [s for s in sqlparse.parse(sql) if str(s).strip()]
    if len(statements) != 1:
        return False

    formatted = sqlparse.format(str(statements[0]), strip_comments=True).strip()
    if not formatted:
        return False
    formatted = formatted.lstrip("(").strip()
    first = formatted.split()[0].upper()
    return first in _ALLOWED


def referenced_tables(sql: str) -> set[str]:
    """Base table names referenced by FROM/JOIN, excluding CTE names."""
    if not sql or not sql.strip():
        return set()
    formatted = sqlparse.format(sql, strip_comments=True)
    cte_names = {m.group(1).lower() for m in _CTE_NAME.finditer(formatted)}
    tables: set[str] = set()
    for match in _FROM_JOIN.finditer(formatted):
        name = match.group(1).lower()
        if name in {"select", "lateral"} or name in cte_names:
            continue
        tables.add(name)
    return tables


def tables_are_allowed(sql: str) -> bool:
    """True when every referenced table is in the analytical allow-list."""
    return referenced_tables(sql) <= ALLOWED_TABLES


def is_allowed_query(sql: str) -> bool:
    return is_read_only_sql(sql) and tables_are_allowed(sql)
