"""Start the StockJarvis chat server."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.agent import create_agent
from app.config import database_url_from_env
from app.server import create_app, run_app

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    env_path = ROOT / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except ImportError:
        pass


def main() -> None:
    load_env()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    database_url = database_url_from_env()
    if not database_url:
        raise RuntimeError("Set DATABASE_URL or PGHOST/PGDATABASE/PGUSER.")
    agent = create_agent()
    print("StockJarvis: Claude (AI Credits) + Postgres")
    app = create_app(agent, database_url)
    run_app(app, host=host, port=port)


if __name__ == "__main__":
    main()
