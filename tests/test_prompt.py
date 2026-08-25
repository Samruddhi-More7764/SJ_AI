from app.prompt import build_system_prompt
from app.sql_guard import FALLBACK_MESSAGE


def test_prompt_contains_fallback_and_schema():
    text = build_system_prompt("2026-08-24", schema_text="table filings (company text)")
    assert FALLBACK_MESSAGE in text
    assert "table filings (company text)" in text
    assert "2026-08-24" in text
    assert "StockJarvis" in text


def test_prompt_requires_one_sql_then_stop():
    text = build_system_prompt("2026-08-24")
    lower = text.lower()
    assert "at most once" in lower
    assert "do not retry" in lower
    assert "metric_tag_mappings" in text
    assert "visualize_data" in lower
    assert "hbar" in lower
    assert "company_name" in text
    assert "run_sql" in lower
    assert "processing_status" in text
    assert "rounding_level" in text
    assert "t.qname" in text
    assert "Follow-ups inherit" in text
