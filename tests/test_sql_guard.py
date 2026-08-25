"""Read-only SQL guard — filings DB must not accept writes."""

from app.sql_guard import FALLBACK_MESSAGE, is_read_only_sql


def test_select_is_allowed():
    assert is_read_only_sql("SELECT * FROM filings WHERE company = 'RELIANCE'")


def test_select_with_leading_whitespace_and_comment():
    sql = """
    -- quarterly revenue
    SELECT revenue FROM filings
    """
    assert is_read_only_sql(sql)


def test_cte_is_allowed():
    assert is_read_only_sql(
        "WITH t AS (SELECT 1 AS x) SELECT x FROM t"
    )


def test_insert_is_rejected():
    assert not is_read_only_sql("INSERT INTO filings VALUES (1)")


def test_update_is_rejected():
    assert not is_read_only_sql("UPDATE filings SET revenue = 0")


def test_delete_is_rejected():
    assert not is_read_only_sql("DELETE FROM filings")


def test_drop_is_rejected():
    assert not is_read_only_sql("DROP TABLE filings")


def test_multiple_statements_rejected():
    assert not is_read_only_sql("SELECT 1; DELETE FROM filings")


def test_empty_sql_rejected():
    assert not is_read_only_sql("")
    assert not is_read_only_sql("   ")


def test_fallback_copy_is_exact():
    assert FALLBACK_MESSAGE == "This information is not with us."


def test_analytical_tables_are_allowed():
    from app.sql_guard import tables_are_allowed

    sql = """
    SELECT c.company_name FROM companies c
    JOIN filings f ON f.company_id = c.company_id
    JOIN financial_facts ff ON ff.filing_id = f.filing_id
    """
    assert tables_are_allowed(sql)


def test_query_log_and_report_cache_are_rejected():
    from app.sql_guard import tables_are_allowed

    assert not tables_are_allowed("SELECT * FROM query_log")
    assert not tables_are_allowed("SELECT * FROM report_cache")


def test_cte_without_base_tables_is_allowed():
    from app.sql_guard import tables_are_allowed

    assert tables_are_allowed("WITH t AS (SELECT 1 AS x) SELECT x FROM t")


def test_select_without_from_is_allowed():
    from app.sql_guard import tables_are_allowed

    assert tables_are_allowed("SELECT 1")
