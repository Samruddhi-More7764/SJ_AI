from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.catalog import clamp_limit, like_pattern


def test_clamp_limit():
    assert clamp_limit(None) == 100
    assert clamp_limit(10) == 10
    assert clamp_limit(0) == 1
    assert clamp_limit(5000) == 200


def test_like_pattern_escapes_wildcards():
    assert like_pattern("SBIN") == "%SBIN%"
    assert like_pattern("100%") == r"%100\%%"
    assert like_pattern("a_b") == r"%a\_b%"


def test_app_routes_and_branding():
    from app.server import create_app

    app = create_app(MagicMock(), database_url="postgresql://unused")
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/chat" in paths
    assert "/api/vanna/v2/chat_sse" in paths
    assert "/api/catalog/summary" in paths
    assert "/api/catalog/companies" in paths
    assert "/api/catalog/tags" in paths
    assert "/health" in paths
    assert "/" in paths

    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "healthy", "service": "stockjarvis"}

    home = client.get("/")
    assert home.status_code == 200
    html = home.text
    assert "StockJarvis" in html
    assert "Ask the filings" in html
    assert "vanna-chat" not in html.lower()
    assert "Vanna" not in html
    assert "API Endpoints" not in html
    assert "styles.css?v=3" in html
    assert "app.js?v=3" in html


def test_catalog_summary_endpoint():
    from app.server import create_app

    fake = {
        "company_count": 83,
        "filing_count": 98,
        "period_start": "2018-03-31",
        "period_end": "2018-09-30",
        "tag_count": 12,
        "approved_tag_count": 10,
    }
    app = create_app(MagicMock(), database_url="postgresql://unused")
    with patch("app.server.fetch_summary", return_value=fake):
        client = TestClient(app)
        response = client.get("/api/catalog/summary")
    assert response.status_code == 200
    assert response.json()["company_count"] == 83


def test_catalog_companies_passes_query():
    from app.server import create_app

    app = create_app(MagicMock(), database_url="postgresql://unused")
    with patch(
        "app.server.fetch_companies",
        return_value=[{"company_name": "State Bank of India", "symbol": "SBIN"}],
    ) as mocked:
        client = TestClient(app)
        response = client.get("/api/catalog/companies", params={"q": "sbin", "limit": 10})
    assert response.status_code == 200
    mocked.assert_called_once()
    assert mocked.call_args.kwargs["q"] == "sbin"
    assert mocked.call_args.kwargs["limit"] == 10
    assert response.json()["companies"][0]["symbol"] == "SBIN"


def test_provenance_sse_payload_shape():
    from app.server import provenance_sse_payload

    payload = provenance_sse_payload("c1", "r1", {"source": "value_numeric"})
    assert payload["rich"]["type"] == "provenance"
    assert payload["rich"]["data"]["source"] == "value_numeric"
    assert payload["conversation_id"] == "c1"


def test_tag_scroller_and_provenance_in_static_js():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "app" / "web" / "app.js").read_text()
    assert "How these numbers were produced" in js
    assert "type === \"provenance\"" in js
    assert "row.meaning || row.qname" not in js
    assert "insertIntoComposer(qname)" in js
