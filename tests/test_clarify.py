from app.clarify import (
    clarification_text,
    extract_companies,
    extract_metric,
    extract_period,
    is_exploratory,
    is_ranking,
    merge_state,
    missing_slots,
    parse_clarify_json,
)
from app.conversation import ConversationState

CATALOG = [
    ("State Bank of India", "SBIN"),
    ("Tata Consultancy Services Limited", "TCS"),
]


def test_extract_metric_and_period():
    assert extract_metric("show me SBI revenue") == "revenue"
    assert extract_period("Q1 2018 revenue") == "Q1"
    assert extract_period("latest filings") == "latest"


def test_extract_company_by_symbol():
    assert extract_companies("show SBIN revenue", CATALOG) == ["SBIN"]


def test_list_companies_is_exploratory():
    assert is_exploratory("List five company names and their symbols from the database.")
    assert not is_exploratory("show me SBI revenue")


def test_missing_company_and_period_on_metric_question():
    state = merge_state(ConversationState(), "show revenue", CATALOG)
    assert missing_slots(state, "show revenue") == ["company", "period"]


def test_follow_up_inherits_metric_and_period():
    prior = ConversationState(
        companies=["SBIN"], metrics=["revenue"], period="latest"
    )
    merged = merge_state(prior, "what about TCS?", CATALOG)
    assert merged.companies == ["TCS"]
    assert merged.metrics == ["revenue"]
    assert merged.period == "latest"
    assert missing_slots(merged, "what about TCS?") == []


def test_ranking_does_not_require_company_in_fallback():
    message = "top 10 companies by revenue"
    assert is_ranking(message)
    state = merge_state(ConversationState(), message, CATALOG)
    assert missing_slots(state, message) == []
    assert not is_ranking("show revenue")


def test_clarification_asks_for_company():
    assert "company" in clarification_text("company").lower()


def test_parse_ranking_does_not_require_company():
    decision = parse_clarify_json(
        '{"ready": true, "intent": "ranking", "companies": [], '
        '"metrics": ["revenue"], "period": "latest", "question": null}'
    )
    assert decision.ready is True
    assert decision.intent == "ranking"
    assert decision.companies == []
    assert decision.metrics == ["revenue"]


def test_parse_clarify_question():
    decision = parse_clarify_json(
        '{"ready": false, "intent": "single_fact", "companies": [], '
        '"metrics": ["revenue"], "period": null, '
        '"question": "Which NSE symbol should I use?"}'
    )
    assert decision.ready is False
    assert "symbol" in (decision.question or "").lower()
