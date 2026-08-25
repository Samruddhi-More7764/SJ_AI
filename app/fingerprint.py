"""Cheap filings-database fingerprint so answer cache can version-bust."""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from app.catalog import _connect, _iso

Fingerprint = Dict[str, Any]


def version_from_stats(stats: Fingerprint) -> str:
    payload = "|".join(
        [
            str(stats.get("company_count") or 0),
            str(stats.get("filing_count") or 0),
            str(stats.get("fact_count") or 0),
            str(stats.get("max_period_end") or ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def data_fingerprint(database_url: str) -> Fingerprint:
    conn, cursor = _connect(database_url)
    try:
        cursor.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM companies) AS company_count,
              (SELECT COUNT(*) FROM filings WHERE processing_status = 'Processed')
                AS filing_count,
              (SELECT COUNT(*) FROM financial_facts) AS fact_count,
              (SELECT MAX(period_end) FROM filings
                 WHERE processing_status = 'Processed') AS max_period_end
            """
        )
        row = cursor.fetchone() or {}
        conn.rollback()
        return {
            "company_count": int(row.get("company_count") or 0),
            "filing_count": int(row.get("filing_count") or 0),
            "fact_count": int(row.get("fact_count") or 0),
            "max_period_end": _iso(row.get("max_period_end")),
        }
    finally:
        cursor.close()
        conn.close()


def fingerprint_version(database_url: str) -> str:
    return version_from_stats(data_fingerprint(database_url))


def fetch_derived_formulas(database_url: str) -> Dict[str, str]:
    conn, cursor = _connect(database_url)
    try:
        cursor.execute(
            """
            SELECT metric_name, formula
            FROM derived_metric_definitions
            WHERE formula IS NOT NULL
              AND (
                status IS NULL
                OR lower(status) IN ('approved', 'active')
              )
            """
        )
        rows = cursor.fetchall() or []
        conn.rollback()
        return {
            str(row["metric_name"]): str(row["formula"])
            for row in rows
            if row.get("metric_name") and row.get("formula")
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return {}
    finally:
        cursor.close()
        conn.close()
