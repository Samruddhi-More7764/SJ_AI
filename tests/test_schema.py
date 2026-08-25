from app.schema import format_schema


def test_format_schema_groups_columns():
    rows = [
        {"table_name": "filings", "column_name": "company", "data_type": "text"},
        {"table_name": "filings", "column_name": "revenue", "data_type": "numeric"},
        {"table_name": "periods", "column_name": "year", "data_type": "integer"},
    ]
    text = format_schema(rows)
    assert "TABLE filings (company text, revenue numeric)" in text
    assert "TABLE periods (year integer)" in text


def test_format_schema_empty():
    assert format_schema([]) == "(no public tables found)"
