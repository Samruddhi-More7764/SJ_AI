import pytest
from vanna.core.storage import Conversation
from vanna.core.user import User

from app.cache import AnswerCache
from app.clarify import ClarifyDecision
from app.workflow import StockJarvisWorkflowHandler

CATALOG = [("State Bank of India", "SBIN"), ("Tata Consultancy Services Limited", "TCS")]


async def _ask_company(message, state, history, user):
    return ClarifyDecision(
        ready=False,
        intent="single_fact",
        metrics=["revenue"],
        question="Which company should I use? Please give an NSE name or symbol.",
    )


async def _ready(message, state, history, user):
    return ClarifyDecision(
        ready=True,
        intent="single_fact",
        companies=["SBIN"],
        metrics=["revenue"],
        period="latest",
    )


@pytest.fixture
def handler(tmp_path):
    return StockJarvisWorkflowHandler(
        catalog=CATALOG,
        cache=AnswerCache(tmp_path / "cache"),
        welcome_message="hi",
        conversations_dir=tmp_path / "conversations",
        clarify_fn=_ask_company,
    )


def _conversation():
    return Conversation(
        id="c1",
        user=User(id="local", username="stockjarvis", group_memberships=["user"]),
        messages=[],
    )


@pytest.mark.asyncio
async def test_clarify_skips_llm_when_company_missing(handler):
    result = await handler.try_handle(
        None, _conversation().user, _conversation(), "show revenue"
    )
    assert result.should_skip_llm is True
    text = result.components[0].rich_component.content.lower()
    assert "company" in text


@pytest.mark.asyncio
async def test_show_revenue_asks_company_even_if_llm_says_ranking(tmp_path):
    async def pretend_ranking(message, state, history, user):
        return ClarifyDecision(
            ready=True,
            intent="ranking",
            metrics=["revenue"],
            period="latest",
        )

    handler = StockJarvisWorkflowHandler(
        catalog=CATALOG,
        cache=AnswerCache(tmp_path / "cache"),
        welcome_message="hi",
        conversations_dir=tmp_path / "conversations",
        clarify_fn=pretend_ranking,
    )
    result = await handler.try_handle(
        None, _conversation().user, _conversation(), "show revenue"
    )
    assert result.should_skip_llm is True
    text = result.components[0].rich_component.content.lower()
    assert "company" in text


@pytest.mark.asyncio
async def test_ranking_skips_clarify_llm(tmp_path):
    calls = []

    async def track(message, state, history, user):
        calls.append(message)
        return ClarifyDecision(
            ready=True, intent="ranking", metrics=["revenue"], period="latest"
        )

    handler = StockJarvisWorkflowHandler(
        catalog=CATALOG,
        cache=AnswerCache(tmp_path / "cache"),
        welcome_message="hi",
        conversations_dir=tmp_path / "conversations",
        clarify_fn=track,
    )
    result = await handler.try_handle(
        None,
        _conversation().user,
        _conversation(),
        "top 10 companies by revenue",
    )
    assert calls == []
    assert result.should_skip_llm is False


@pytest.mark.asyncio
async def test_cache_hit_skips_llm(tmp_path):
    handler = StockJarvisWorkflowHandler(
        catalog=CATALOG,
        cache=AnswerCache(tmp_path / "cache"),
        welcome_message="hi",
        conversations_dir=tmp_path / "conversations",
        clarify_fn=_ready,
    )
    handler.cache.put(
        "sbin revenue latest",
        {"markdown": "cached sbi", "rows": [{"symbol": "SBIN"}]},
    )
    user = User(id="local", username="stockjarvis", group_memberships=["user"])
    conv = Conversation(id="c1", user=user, messages=[])
    result = await handler.try_handle(None, user, conv, "SBIN revenue latest")
    assert result.should_skip_llm is True
    blob = str(result.components)
    assert "cached" in blob.lower() or "SBIN" in blob


@pytest.mark.asyncio
async def test_cache_hit_replays_provenance(tmp_path):
    handler = StockJarvisWorkflowHandler(
        catalog=CATALOG,
        cache=AnswerCache(tmp_path / "cache"),
        welcome_message="hi",
        conversations_dir=tmp_path / "conversations",
        clarify_fn=_ready,
    )
    handler.cache.put(
        "sbin revenue latest",
        {
            "markdown": "cached sbi",
            "rows": [{"symbol": "SBIN"}],
            "provenance": {
                "source": "value_numeric from filings via approved metric mappings",
                "tags": ["in-bse-fin:RevenueFromOperations"],
                "sql": "SELECT 1",
            },
        },
    )
    user = User(id="local", username="stockjarvis", group_memberships=["user"])
    conv = Conversation(id="c1", user=user, messages=[])
    result = await handler.try_handle(None, user, conv, "SBIN revenue latest")
    types = [
        component.rich_component.serialize_for_frontend()["type"]
        for component in result.components
    ]
    assert "provenance" in types
