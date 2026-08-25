"""Tests that do not need Postgres or Claude."""

import pytest

from app.agent import MAX_TOOL_ITERATIONS, create_agent


def test_tool_iteration_cap_is_one_sql_plus_optional_chart():
    assert MAX_TOOL_ITERATIONS == 3


def test_create_agent_requires_api_key(monkeypatch):
    monkeypatch.delenv("AICREDITS_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("PGHOST", "localhost")
    monkeypatch.setenv("PGDATABASE", "sj_bot_db")
    monkeypatch.setenv("PGUSER", "samruddhimore")
    monkeypatch.setenv("PGPASSWORD", "x")
    with pytest.raises(RuntimeError, match="AICREDITS_API_KEY"):
        create_agent()


def test_create_agent_requires_database(monkeypatch):
    monkeypatch.setenv("AICREDITS_API_KEY", "sk-test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv("PGDATABASE", raising=False)
    monkeypatch.delenv("PGUSER", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL or PGHOST"):
        create_agent()
