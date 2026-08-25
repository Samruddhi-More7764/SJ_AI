from pathlib import Path

from app.cache import AnswerCache, normalize_question


def test_normalize_collapses_whitespace_and_case():
    assert normalize_question("  SBI   Revenue ") == "sbi revenue"


def test_cache_roundtrip(tmp_path: Path):
    cache = AnswerCache(tmp_path)
    cache.put("SBI revenue", {"markdown": "hello", "rows": [{"a": 1}]})
    hit = cache.get("sbi   revenue")
    assert hit is not None
    assert hit["markdown"] == "hello"
    assert hit["rows"] == [{"a": 1}]


def test_cache_miss(tmp_path: Path):
    cache = AnswerCache(tmp_path)
    assert cache.get("never asked") is None


def test_stale_data_version_is_a_miss_and_deletes_file(tmp_path: Path):
    cache = AnswerCache(tmp_path, data_version="v1")
    cache.put("top 10 companies by revenue", {"markdown": "old", "rows": [{"n": 1}]})
    stale = AnswerCache(tmp_path, data_version="v2")
    assert stale.get("top 10 companies by revenue") is None
    assert list(tmp_path.glob("*.json")) == []
