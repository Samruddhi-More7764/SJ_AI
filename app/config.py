"""Environment helpers for StockJarvis."""

from __future__ import annotations

import os
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def normalize_database_url(url: str) -> str:
    """psycopg2 wants postgresql://; Render remote hosts need SSL."""
    normalized = (url or "").strip()
    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized[len("postgres://") :]
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()
    if not host or host in _LOCAL_HOSTS:
        return normalized
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    keys = {key.lower() for key, _ in query_items}
    if "sslmode" in keys:
        return normalized
    query_items.append(("sslmode", "require"))
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def database_url_from_env() -> str | None:
    url = os.environ.get("DATABASE_URL")
    if url:
        return normalize_database_url(url)

    host = os.environ.get("PGHOST")
    database = os.environ.get("PGDATABASE")
    user = os.environ.get("PGUSER")
    if not (host and database and user):
        return None

    password = os.environ.get("PGPASSWORD", "")
    port = os.environ.get("PGPORT", "5432")
    assembled = (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{database}"
    )
    return normalize_database_url(assembled)


def llm_settings_from_env() -> tuple[str, str, str]:
    """Return (api_key, base_url, model) for the OpenAI-compatible Claude proxy."""
    api_key = os.environ.get("AICREDITS_API_KEY") or os.environ.get(
        "ANTHROPIC_API_KEY"
    )
    if not api_key:
        raise RuntimeError("AICREDITS_API_KEY is not set.")
    base_url = os.environ.get(
        "AICREDITS_BASE_URL", "https://api.aicredits.in/v1"
    )
    model = os.environ.get(
        "AICREDITS_MODEL", "anthropic/claude-sonnet-4.5"
    )
    return api_key, base_url, model
