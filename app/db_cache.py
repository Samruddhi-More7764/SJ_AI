"""Postgres answer cache on query_log + report_cache. LLM never queries these."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import psycopg2
import psycopg2.extras

from app.cache import cache_key, jsonable, normalize_question, sql_hash
from app.fingerprint import fingerprint_version
from app.provenance import fact_ids_from_rows

logger = logging.getLogger("stockjarvis")
STATEMENT_TIMEOUT = "15s"

VersionFn = Callable[[], Optional[str]]


def _write_connect(database_url: str):
    conn = psycopg2.connect(database_url, connect_timeout=5)
    conn.autocommit = False
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
    return conn, cursor


def unique_row_values(rows: Sequence[Dict[str, Any]], key: str) -> List[str]:
    seen = []
    found = set()
    for row in rows or []:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in found:
            continue
        found.add(text)
        seen.append(text)
    return seen


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def period_bounds(
    rows: Sequence[Dict[str, Any]],
) -> Tuple[Optional[date], Optional[date]]:
    starts = [_parse_date(row.get("period_start")) for row in rows or []]
    ends = [_parse_date(row.get("period_end")) for row in rows or []]
    start_vals = [item for item in starts if item is not None]
    end_vals = [item for item in ends if item is not None]
    return (
        min(start_vals) if start_vals else None,
        max(end_vals) if end_vals else None,
    )


def chart_type_of(chart: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(chart, dict):
        return None
    traces = chart.get("data") or []
    if not traces or not isinstance(traces[0], dict):
        return None
    first = traces[0]
    if first.get("orientation") == "h":
        return "hbar"
    kind = first.get("type")
    return str(kind) if kind else None


def lookup_company_id(cursor, rows: Sequence[Dict[str, Any]]) -> Optional[str]:
    names = unique_row_values(rows, "company_name")
    symbols = unique_row_values(rows, "symbol")
    if len(names) > 1 or len(symbols) > 1:
        return None
    name = names[0] if names else None
    symbol = symbols[0] if symbols else None
    if not name and not symbol:
        return None
    cursor.execute(
        """
        SELECT company_id
        FROM companies
        WHERE (%s IS NOT NULL AND company_name = %s)
           OR (%s IS NOT NULL AND symbol = %s)
        LIMIT 2
        """,
        (name, name, symbol, symbol),
    )
    found = cursor.fetchall() or []
    if len(found) != 1:
        return None
    company_id = found[0].get("company_id")
    return str(company_id) if company_id else None


def tags_used_payload(payload: Dict[str, Any], rows: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    provenance = payload.get("provenance") or {}
    tags = provenance.get("tags") or unique_row_values(rows, "qname")
    return [{"qname": tag} for tag in tags]


def rendered_report_record(
    question: str,
    payload: Dict[str, Any],
    data_version: Optional[str],
) -> Dict[str, Any]:
    return jsonable(
        {
            **payload,
            "question": question,
            "normalized": normalize_question(question),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "data_version": data_version,
        }
    )


def insert_query_log(
    cursor,
    *,
    question: str,
    sql: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    cache_hit: bool = False,
    status: str = "VALID",
) -> None:
    payload = payload or {}
    rows = payload.get("rows") or []
    cursor.execute(
        """
        INSERT INTO query_log (
          question, resolved_intent, tags_used, sql_hash, status,
          session_id, cache_hit
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            question,
            None,
            psycopg2.extras.Json(tags_used_payload(payload, rows)),
            sql_hash(sql or "") if sql else None,
            status,
            session_id,
            cache_hit,
        ),
    )


def upsert_report_cache(
    cursor,
    *,
    question: str,
    payload: Dict[str, Any],
    data_version: Optional[str],
    intent_hash: Optional[str] = None,
) -> str:
    intent = intent_hash or cache_key(question)
    rows = payload.get("rows") or []
    period_start, period_end = period_bounds(rows)
    company_id = lookup_company_id(cursor, rows)
    fact_ids = fact_ids_from_rows(rows)
    rendered = rendered_report_record(question, payload, data_version)
    cursor.execute(
        """
        INSERT INTO report_cache (
          intent_hash, company_id, period_start, period_end, chart_type,
          rendered_report, source_fact_ids, invalidated_at, created_at
        ) VALUES (
          %s, %s, %s, %s, %s, %s, %s, NULL, NOW()
        )
        ON CONFLICT (intent_hash) DO UPDATE SET
          company_id = EXCLUDED.company_id,
          period_start = EXCLUDED.period_start,
          period_end = EXCLUDED.period_end,
          chart_type = EXCLUDED.chart_type,
          rendered_report = EXCLUDED.rendered_report,
          source_fact_ids = EXCLUDED.source_fact_ids,
          invalidated_at = NULL,
          created_at = NOW()
        """,
        (
            intent,
            company_id,
            period_start,
            period_end,
            chart_type_of(payload.get("chart")),
            psycopg2.extras.Json(rendered),
            fact_ids,
        ),
    )
    return intent


def invalidate_report(cursor, intent_hash: str) -> None:
    cursor.execute(
        """
        UPDATE report_cache
        SET invalidated_at = NOW()
        WHERE intent_hash = %s AND invalidated_at IS NULL
        """,
        (intent_hash,),
    )


class PostgresAnswerCache:
    """Source of truth for StockJarvis answers: report_cache + query_log."""

    def __init__(
        self,
        database_url: str,
        data_version_fn: Optional[VersionFn] = None,
        derived_formulas_fn: Optional[Callable[[], Dict[str, str]]] = None,
    ) -> None:
        self.database_url = database_url
        self.data_version_fn = data_version_fn or (
            lambda: fingerprint_version(database_url)
        )
        self.derived_formulas_fn = derived_formulas_fn
        self._formulas: Optional[Dict[str, str]] = None

    def current_version(self) -> Optional[str]:
        return self.data_version_fn()

    def derived_formulas(self) -> Dict[str, str]:
        if self.derived_formulas_fn is not None:
            return self.derived_formulas_fn() or {}
        if self._formulas is None:
            from app.fingerprint import fetch_derived_formulas

            try:
                self._formulas = fetch_derived_formulas(self.database_url)
            except Exception:
                logger.warning("event=derived_formulas_failed", exc_info=True)
                self._formulas = {}
        return self._formulas

    def get(
        self, question: str, session_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        intent = cache_key(question)
        try:
            version = self.current_version()
        except Exception:
            logger.warning("event=cache_fingerprint_failed", exc_info=True)
            version = None
        conn = None
        cursor = None
        try:
            conn, cursor = _write_connect(self.database_url)
            cursor.execute(
                """
                SELECT rendered_report, invalidated_at
                FROM report_cache
                WHERE intent_hash = %s
                """,
                (intent,),
            )
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                return None
            report = row.get("rendered_report") or {}
            if not isinstance(report, dict):
                conn.rollback()
                return None
            stale = row.get("invalidated_at") is not None
            stored_version = report.get("data_version")
            if version is not None and (stale or stored_version != version):
                invalidate_report(cursor, intent)
                conn.commit()
                return None
            insert_query_log(
                cursor,
                question=question,
                sql=report.get("sql"),
                payload=report,
                session_id=session_id,
                cache_hit=True,
            )
            conn.commit()
            return report
        except Exception:
            logger.warning("event=cache_get_failed", exc_info=True)
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return None
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                conn.close()

    def put(
        self,
        question: str,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
        write_query_log: bool = True,
    ) -> None:
        try:
            version = self.current_version()
        except Exception:
            logger.warning("event=cache_fingerprint_failed", exc_info=True)
            version = None
        conn = None
        cursor = None
        try:
            conn, cursor = _write_connect(self.database_url)
            upsert_report_cache(
                cursor,
                question=question,
                payload=payload,
                data_version=version,
            )
            if write_query_log:
                insert_query_log(
                    cursor,
                    question=question,
                    sql=payload.get("sql"),
                    payload=payload,
                    session_id=session_id,
                    cache_hit=False,
                )
            conn.commit()
        except Exception:
            logger.warning("event=cache_put_failed", exc_info=True)
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                conn.close()
