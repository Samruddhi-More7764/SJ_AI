from app.fingerprint import version_from_stats


def test_version_from_stats_is_stable():
    stats = {
        "company_count": 83,
        "filing_count": 98,
        "fact_count": 1200,
        "max_period_end": "2020-09-30",
    }
    first = version_from_stats(stats)
    second = version_from_stats(dict(stats))
    assert first == second
    assert len(first) == 64


def test_version_changes_when_filings_change():
    base = {
        "company_count": 83,
        "filing_count": 98,
        "fact_count": 1200,
        "max_period_end": "2020-09-30",
    }
    newer = dict(base)
    newer["filing_count"] = 99
    assert version_from_stats(base) != version_from_stats(newer)
