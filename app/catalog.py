"""Read-only catalog queries for the StockJarvis sidebar."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

STATEMENT_TIMEOUT = "15s"
DEFAULT_LIMIT = 100
MAX_LIMIT = 200


def clamp_limit(limit: Optional[int], default: int = DEFAULT_LIMIT, maximum: int = MAX_LIMIT) -> int:
    if limit is None:
        return default
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def like_pattern(query: str) -> str:
    escaped = (
        (query or "")
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _connect(database_url: str):
    conn = psycopg2.connect(database_url, connect_timeout=5)
    conn.autocommit = False
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
    return conn, cursor


def fetch_summary(database_url: str) -> Dict[str, Any]:
    conn, cursor = _connect(database_url)
    try:
        cursor.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM companies) AS company_count,
              (SELECT COUNT(*) FROM filings WHERE processing_status = 'Processed')
                AS filing_count,
              (SELECT MIN(period_start) FROM filings
                 WHERE processing_status = 'Processed') AS period_start,
              (SELECT MAX(period_end) FROM filings
                 WHERE processing_status = 'Processed') AS period_end,
              (SELECT COUNT(*) FROM tag_catalog) AS tag_count,
              (SELECT COUNT(*) FROM tag_catalog WHERE status = 'APPROVED')
                AS approved_tag_count
            """
        )
        row = cursor.fetchone() or {}
        conn.rollback()
        return {
            "company_count": int(row.get("company_count") or 0),
            "filing_count": int(row.get("filing_count") or 0),
            "period_start": _iso(row.get("period_start")),
            "period_end": _iso(row.get("period_end")),
            "tag_count": int(row.get("tag_count") or 0),
            "approved_tag_count": int(row.get("approved_tag_count") or 0),
        }
    finally:
        cursor.close()
        conn.close()


def fetch_companies(
    database_url: str, q: str = "", limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    cap = clamp_limit(limit)
    conn, cursor = _connect(database_url)
    try:
        query = (q or "").strip()
        if query:
            pattern = like_pattern(query)
            cursor.execute(
                """
                SELECT company_name, symbol
                FROM companies
                WHERE company_name ILIKE %s ESCAPE '\\'
                   OR COALESCE(symbol, '') ILIKE %s ESCAPE '\\'
                   OR EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements_text(
                            CASE
                              WHEN jsonb_typeof(COALESCE(aliases, '[]'::jsonb)) = 'array'
                              THEN aliases
                              ELSE '[]'::jsonb
                            END
                        ) AS alias
                        WHERE alias ILIKE %s ESCAPE '\\'
                   )
                ORDER BY company_name
                LIMIT %s
                """,
                (pattern, pattern, pattern, cap),
            )
        else:
            cursor.execute(
                """
                SELECT company_name, symbol
                FROM companies
                WHERE company_name IS NOT NULL
                ORDER BY company_name
                LIMIT %s
                """,
                (cap,),
            )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.rollback()
        return rows
    finally:
        cursor.close()
        conn.close()


def fetch_tags(
    database_url: str, q: str = "", limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    cap = clamp_limit(limit)
    conn, cursor = _connect(database_url)
    try:
        query = (q or "").strip()
        if query:
            pattern = like_pattern(query)
            cursor.execute(
                """
                SELECT DISTINCT ON (t.qname)
                  t.qname, t.meaning, t.category, t.status, m.metric_name
                FROM tag_catalog t
                LEFT JOIN metric_tag_mappings m
                  ON m.tag_id = t.tag_id AND m.status = 'APPROVED'
                WHERE t.qname ILIKE %s ESCAPE '\\'
                   OR COALESCE(t.meaning, '') ILIKE %s ESCAPE '\\'
                   OR COALESCE(m.metric_name, '') ILIKE %s ESCAPE '\\'
                ORDER BY t.qname, m.priority NULLS LAST
                LIMIT %s
                """,
                (pattern, pattern, pattern, cap),
            )
        else:
            cursor.execute(
                """
                SELECT DISTINCT ON (t.qname)
                  t.qname, t.meaning, t.category, t.status, m.metric_name
                FROM tag_catalog t
                LEFT JOIN metric_tag_mappings m
                  ON m.tag_id = t.tag_id AND m.status = 'APPROVED'
                ORDER BY t.qname, m.priority NULLS LAST
                LIMIT %s
                """,
                (cap,),
            )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.rollback()
        return rows
    finally:
        cursor.close()
        conn.close()
