from datetime import date
from unittest.mock import MagicMock

from app.cache import cache_key
from app.db_cache import (
    PostgresAnswerCache,
    chart_type_of,
    period_bounds,
    unique_row_values,
)


def test_unique_and_period_and_chart_helpers():
    rows = [
        {
            "company_name": "State Bank of India",
            "symbol": "SBIN",
            "period_start": "2020-04-01",
            "period_end": "2020-09-30",
        },
        {
            "company_name": "State Bank of India",
            "symbol": "SBIN",
            "period_start": "2020-04-01",
            "period_end": "2020-06-30",
        },
    ]
    assert unique_row_values(rows, "symbol") == ["SBIN"]
    start, end = period_bounds(rows)
    assert start == date(2020, 4, 1)
    assert end == date(2020, 9, 30)
    assert (
        chart_type_of({"data": [{"type": "bar", "orientation": "h"}]}) == "hbar"
    )


def test_postgres_get_miss_on_version_mismatch():
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "rendered_report": {"markdown": "old", "data_version": "v1"},
        "invalidated_at": None,
    }
    cursor.fetchall.return_value = []
    conn = MagicMock()
    cache = PostgresAnswerCache(
        "postgresql://unused", data_version_fn=lambda: "v2"
    )
    with _patch_connect(conn, cursor):
        assert cache.get("top 10 companies by revenue") is None
    sql = " ".join(str(call.args[0]) for call in cursor.execute.call_args_list)
    assert "invalidated_at" in sql.lower()
    conn.commit.assert_called()


def test_postgres_get_hit_logs_cache_hit():
    report = {
        "markdown": "cached",
        "data_version": "v1",
        "sql": "SELECT 1",
        "rows": [{"qname": "in-bse-fin:RevenueFromOperations"}],
    }
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "rendered_report": report,
        "invalidated_at": None,
    }
    conn = MagicMock()
    cache = PostgresAnswerCache(
        "postgresql://unused", data_version_fn=lambda: "v1"
    )
    with _patch_connect(conn, cursor):
        hit = cache.get("SBI revenue", session_id="c1")
    assert hit["markdown"] == "cached"
    inserted = cursor.execute.call_args_list[-1]
    assert "query_log" in inserted.args[0]
    assert inserted.args[1][-1] is True
    conn.commit.assert_called()


def test_postgres_put_upserts_report_and_logs_miss():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn = MagicMock()
    cache = PostgresAnswerCache(
        "postgresql://unused", data_version_fn=lambda: "v1"
    )
    with _patch_connect(conn, cursor):
        cache.put(
            "SBI revenue",
            {"markdown": "hello", "sql": "SELECT 1", "rows": [{"a": 1}]},
            session_id="c1",
        )
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("report_cache" in sql for sql in statements)
    assert any("query_log" in sql for sql in statements)
    intent = cache_key("SBI revenue")
    upsert = next(call for call in cursor.execute.call_args_list if "report_cache" in call.args[0])
    assert upsert.args[1][0] == intent
    conn.commit.assert_called()


def _patch_connect(conn, cursor):
    from unittest.mock import patch

    def fake_connect(_url):
        return conn, cursor

    return patch("app.db_cache._write_connect", fake_connect)
