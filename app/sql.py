"""Read-only SQL execution against the filings Postgres database."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, List, Optional, Tuple

import pandas as pd
from vanna.capabilities.sql_runner import RunSqlToolArgs
from vanna.core.tool import ToolContext, ToolResult
from vanna.integrations.postgres import PostgresRunner
from vanna.tools.run_sql import RunSqlTool

from app.sql_guard import FALLBACK_MESSAGE, is_allowed_query, is_read_only_sql

__all__ = [
    "FALLBACK_MESSAGE",
    "FilingsRunSqlTool",
    "MAX_RESULT_ROWS",
    "ReadOnlyPostgresRunner",
    "ReadOnlySqlError",
    "cap_result_rows",
    "is_read_only_sql",
    "llm_text_after_sql",
]

logger = logging.getLogger("stockjarvis")

MAX_RESULT_ROWS = 500
STATEMENT_TIMEOUT = "15s"

_AFTER_SQL = (
    "Do not call run_sql again. Next call visualize_data. "
    "For top-N companies use chart_type=hbar, x=value_numeric, y=company_name. "
    "For one company over time use chart_type=line, x=period_end, y=value_numeric. "
    "For a distribution use chart_type=histogram. Then summarize. Do not invent figures."
)


class ReadOnlySqlError(ValueError):
    """Raised when a non-SELECT statement is blocked."""


def cap_result_rows(rows: List[Any]) -> Tuple[List[Any], bool]:
    if len(rows) > MAX_RESULT_ROWS:
        return rows[:MAX_RESULT_ROWS], True
    return rows, False


def llm_text_after_sql(result_for_llm: str, row_count: Optional[int]) -> str:
    """Rewrite Vanna's SQL tool text so the model charts then stops."""
    if row_count == 0:
        return (
            f"Query returned no rows. Tell the user exactly: {FALLBACK_MESSAGE}"
        )

    preview = result_for_llm.split("**IMPORTANT:")[0]
    preview = preview.replace(
        "THE NEXT STEP SHOULD BE A VISUALIZE_DATA CALL", ""
    ).strip()
    return f"{preview}\n\n{_AFTER_SQL}"


def llm_text_after_sql_error(error_text: str) -> str:
    return (
        f"{error_text}\n\nDo not call run_sql again. "
        f"Tell the user exactly: {FALLBACK_MESSAGE}"
    )


class ReadOnlyPostgresRunner(PostgresRunner):
    """Postgres runner that only fetches SELECT/WITH on allowed tables."""

    def _run_sql_sync(self, sql: str) -> pd.DataFrame:
        if self.connection_string:
            conn = self.psycopg2.connect(self.connection_string, connect_timeout=5)
        else:
            conn = self.psycopg2.connect(**self.connection_params)

        cursor = conn.cursor(cursor_factory=self.psycopg2.extras.RealDictCursor)
        t0 = time.perf_counter()
        try:
            cursor.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            cursor.execute(sql)
            if cursor.description is None:
                conn.rollback()
                raise ReadOnlySqlError("Query did not return a result set.")
            rows, truncated = cap_result_rows(
                list(cursor.fetchmany(MAX_RESULT_ROWS + 1))
            )
            conn.rollback()
            logger.info(
                "event=sql_done elapsed_s=%.3f rows=%s truncated=%s",
                time.perf_counter() - t0,
                len(rows),
                truncated,
            )
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame([dict(row) for row in rows])
        except Exception:
            logger.warning("event=sql_failed elapsed_s=%.3f", time.perf_counter() - t0)
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            cursor.close()
            conn.close()

    async def run_sql(self, args: RunSqlToolArgs, context: ToolContext):
        if not is_allowed_query(args.sql):
            raise ReadOnlySqlError(
                "Only SELECT/WITH on analytical filings tables is allowed."
            )
        logger.info("event=sql_start")
        return await asyncio.to_thread(self._run_sql_sync, args.sql)


class FilingsRunSqlTool(RunSqlTool):
    """RunSqlTool that charts after rows (or the empty fallback)."""

    async def execute(self, context: ToolContext, args: RunSqlToolArgs) -> ToolResult:
        result = await super().execute(context, args)
        if not result.success:
            result.result_for_llm = llm_text_after_sql_error(result.result_for_llm)
            return result

        row_count = (result.metadata or {}).get("row_count")
        result.result_for_llm = llm_text_after_sql(result.result_for_llm, row_count)
        simple = getattr(result.ui_component, "simple_component", None)
        if simple is not None and hasattr(simple, "text"):
            simple.text = result.result_for_llm

        from app.cache import remember_sql_result

        remember_sql_result(
            context.conversation_id,
            sql=args.sql,
            row_count=row_count,
            columns=(result.metadata or {}).get("columns") or [],
            rows=(result.metadata or {}).get("results") or [],
            output_file=(result.metadata or {}).get("output_file"),
        )
        return result
