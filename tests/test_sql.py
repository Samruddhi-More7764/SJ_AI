from app.sql import MAX_RESULT_ROWS, cap_result_rows, llm_text_after_sql
from app.sql_guard import FALLBACK_MESSAGE


def test_empty_rows_tell_llm_the_fallback():
    text = llm_text_after_sql("Query executed successfully. No rows returned.", 0)
    assert FALLBACK_MESSAGE in text
    assert "no rows" in text.lower()


def test_successful_sql_strips_visualize_nudge_and_stops():
    raw = (
        "company_name,symbol\nSBI,SBIN\n\n"
        "Results saved to file: query_results_abc.csv\n\n"
        "**IMPORTANT: FOR VISUALIZE_DATA USE FILENAME: query_results_abc.csv**"
    )
    text = llm_text_after_sql(raw, 1)
    assert "FOR VISUALIZE_DATA USE FILENAME" not in text
    assert "do not call run_sql again" in text.lower()
    assert "SBIN" in text
    assert "visualize_data" in text.lower()
    assert "hbar" in text.lower()


def test_sql_error_tells_llm_not_to_retry():
    from app.sql import llm_text_after_sql_error

    text = llm_text_after_sql_error("Error executing query: column name does not exist")
    assert "do not call run_sql again" in text.lower()
    assert FALLBACK_MESSAGE in text


def test_cap_result_rows():
    rows = [{"i": i} for i in range(MAX_RESULT_ROWS + 50)]
    out, truncated = cap_result_rows(rows)
    assert truncated is True
    assert len(out) == MAX_RESULT_ROWS
    kept, not_truncated = cap_result_rows([{"i": 1}])
    assert not_truncated is False
    assert kept == [{"i": 1}]
