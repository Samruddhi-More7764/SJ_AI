"""Import filesystem answer_cache JSON files into query_log + report_cache."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cache import CACHE_DIR, cache_key
from app.config import database_url_from_env
from app.db_cache import insert_query_log, upsert_report_cache, _write_connect
from app.fingerprint import fingerprint_version
from app.provenance import build_provenance


def load_env() -> None:
    env_path = ROOT / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except ImportError:
        pass


def iter_cache_files(directory: Path) -> List[Path]:
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def load_cache_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        record = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    return record


def migration_log_exists(cursor, question: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM query_log
        WHERE session_id = %s AND question = %s
        LIMIT 1
        """,
        ("migration", question),
    )
    return cursor.fetchone() is not None


def migrate_record(
    cursor,
    path: Path,
    record: Dict[str, Any],
    data_version: str,
    *,
    dry_run: bool,
) -> str:
    question = (record.get("question") or "").strip()
    if not question:
        return "skip-no-question"
    if path.stem != cache_key(question):
        # Still import under the live lookup key so runtime get() hits.
        pass
    if not record.get("provenance") and record.get("sql"):
        record["provenance"] = build_provenance(
            record.get("sql") or "",
            record.get("columns") or [],
            record.get("rows") or [],
        )
    if dry_run:
        return "dry-run"
    upsert_report_cache(
        cursor,
        question=question,
        payload=record,
        data_version=data_version,
        intent_hash=cache_key(question),
    )
    if not migration_log_exists(cursor, question):
        insert_query_log(
            cursor,
            question=question,
            sql=record.get("sql"),
            payload=record,
            session_id="migration",
            cache_hit=False,
        )
    return "upserted"


def migrate_directory(
    directory: Path,
    database_url: str,
    *,
    dry_run: bool = False,
    delete_files: bool = False,
) -> Dict[str, int]:
    files = iter_cache_files(directory)
    counts = {"files": len(files), "upserted": 0, "dry_run": 0, "skipped": 0, "deleted": 0}
    if not files:
        return counts
    if dry_run:
        for path in files:
            record = load_cache_file(path)
            if record is None or not (record.get("question") or "").strip():
                counts["skipped"] += 1
                print(f"skip             {path.name}")
                continue
            question = str(record.get("question"))[:80]
            print(f"{'dry-run':16} {path.name}  {question}")
            counts["dry_run"] += 1
        return counts
    data_version = fingerprint_version(database_url)
    conn, cursor = _write_connect(database_url)
    try:
        for path in files:
            record = load_cache_file(path)
            if record is None:
                counts["skipped"] += 1
                print(f"skip unreadable {path.name}")
                continue
            action = migrate_record(
                cursor, path, record, data_version, dry_run=dry_run
            )
            question = (record.get("question") or path.stem)[:80]
            print(f"{action:16} {path.name}  {question}")
            if action == "dry-run":
                counts["dry_run"] += 1
            elif action == "upserted":
                counts["upserted"] += 1
                if delete_files:
                    path.unlink()
                    counts["deleted"] += 1
            else:
                counts["skipped"] += 1
        if conn is not None:
            conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
    return counts


def main(argv: Optional[Iterable[str]] = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(
        description="Copy ./answer_cache JSON files into sj_bot_db report_cache + query_log."
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=CACHE_DIR,
        help="Directory of {sha256}.json files (default: ./answer_cache)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be imported without writing to Postgres.",
    )
    parser.add_argument(
        "--delete-files",
        action="store_true",
        help="Delete each JSON file after a successful upsert.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    database_url = database_url_from_env()
    if not database_url:
        print("Set DATABASE_URL or PGHOST/PGDATABASE/PGUSER.", file=sys.stderr)
        return 1
    directory = args.cache_dir
    if not directory.exists():
        print(f"No cache directory at {directory}")
        return 0
    counts = migrate_directory(
        directory,
        database_url,
        dry_run=args.dry_run,
        delete_files=args.delete_files,
    )
    print(
        "done files={files} upserted={upserted} dry_run={dry_run} "
        "skipped={skipped} deleted={deleted}".format(**counts)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
