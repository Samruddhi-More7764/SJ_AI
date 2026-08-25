import json
from pathlib import Path

from scripts.migrate_answer_cache import iter_cache_files, load_cache_file, migrate_directory


def test_dry_run_counts_json_files(tmp_path: Path, capsys):
    record = {
        "question": "top 10 companies by revenue",
        "sql": "SELECT 1",
        "rows": [{"company_name": "A"}],
        "markdown": "ok",
    }
    (tmp_path / "abc.json").write_text(json.dumps(record))
    (tmp_path / "skip.txt").write_text("nope")
    counts = migrate_directory(
        tmp_path, "postgresql://unused", dry_run=True, delete_files=False
    )
    assert counts["files"] == 1
    assert counts["dry_run"] == 1
    assert counts["upserted"] == 0
    assert load_cache_file(iter_cache_files(tmp_path)[0])["question"] == record["question"]
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "top 10 companies by revenue" in out
