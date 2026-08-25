from app.prompt import build_system_prompt
from app.schema_knowledge import SCHEMA_PROMPT
from app.sql_guard import FALLBACK_MESSAGE


def test_schema_prompt_is_analytical_not_live_dump():
    assert "companies (" in SCHEMA_PROMPT
    assert "metric_tag_mappings" in SCHEMA_PROMPT
    assert "processing_status = 'Processed'" in SCHEMA_PROMPT
    assert "status = 'APPROVED'" in SCHEMA_PROMPT
    assert "query_log" not in SCHEMA_PROMPT
    assert "report_cache" not in SCHEMA_PROMPT


def test_schema_prompt_matches_live_xbrl_and_rounding_columns():
    assert "dimensions" in SCHEMA_PROMPT
    assert "JSONB" in SCHEMA_PROMPT
    assert "dimension            TEXT" not in SCHEMA_PROMPT
    assert "member               TEXT" not in SCHEMA_PROMPT
    assert "rounding_level" in SCHEMA_PROMPT


def test_default_prompt_embeds_static_schema():
    text = build_system_prompt("2026-08-24")
    assert FALLBACK_MESSAGE in text
    assert SCHEMA_PROMPT.strip() in text
    assert "information_schema" not in text.lower()
