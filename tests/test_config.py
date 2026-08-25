from app.config import database_url_from_env, llm_settings_from_env, normalize_database_url


def test_database_url_from_pg_parts(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PGHOST", "localhost")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGDATABASE", "sj_bot_db")
    monkeypatch.setenv("PGUSER", "samruddhimore")
    monkeypatch.setenv("PGPASSWORD", "secret")
    assert (
        database_url_from_env()
        == "postgresql://samruddhimore:secret@localhost:5432/sj_bot_db"
    )


def test_normalize_postgres_scheme_and_ssl_for_remote():
    raw = "postgres://sjbot:secret@dpg-abc.render.com/sj_bot_db"
    out = normalize_database_url(raw)
    assert out.startswith("postgresql://")
    assert "sslmode=require" in out
    assert "dpg-abc.render.com" in out


def test_normalize_keeps_existing_sslmode_and_localhost():
    local = "postgresql://u:p@localhost:5432/sj_bot_db"
    assert normalize_database_url(local) == local
    already = "postgres://u:p@db.example.com/sj_bot_db?sslmode=verify-full"
    out = normalize_database_url(already)
    assert out.startswith("postgresql://")
    assert "sslmode=verify-full" in out
    assert out.count("sslmode=") == 1


def test_database_url_env_is_normalized(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgres://sjbot:x@dpg-xyz.render.com:5432/sj_bot_db"
    )
    url = database_url_from_env()
    assert url is not None
    assert url.startswith("postgresql://")
    assert "sslmode=require" in url


def test_llm_settings_require_key(monkeypatch):
    monkeypatch.delenv("AICREDITS_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import pytest

    with pytest.raises(RuntimeError, match="AICREDITS_API_KEY"):
        llm_settings_from_env()
