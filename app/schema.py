"""Load table/column names from Postgres for the system prompt."""

from __future__ import annotations

from typing import Any, Sequence

SCHEMA_SQL = """
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position
"""


def format_schema(rows: Sequence[Any]) -> str:
    """Turn information_schema rows into a compact prompt block."""
    tables: dict[str, list[str]] = {}
    for row in rows:
        if isinstance(row, dict):
            name = row["table_name"]
            col = f"{row['column_name']} {row['data_type']}"
        else:
            name, col_name, data_type = row[0], row[1], row[2]
            col = f"{col_name} {data_type}"
        tables.setdefault(name, []).append(col)

    if not tables:
        return "(no public tables found)"

    lines = []
    for table, cols in tables.items():
        lines.append(f"TABLE {table} ({', '.join(cols)})")
    return "\n".join(lines)


def load_schema(database_url: str) -> str:
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(database_url)
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(SCHEMA_SQL)
        rows = cursor.fetchall()
        cursor.close()
        return format_schema(rows)
    finally:
        conn.close()
