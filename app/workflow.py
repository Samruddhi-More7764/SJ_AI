"""Workflow: LLM clarify, then cache, else Claude tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable, List, Optional, Sequence

from vanna.components import (
    ChartComponent,
    DataFrameComponent,
    RichTextComponent,
    SimpleTextComponent,
    UiComponent,
)
from vanna.core.storage import Conversation, Message
from vanna.core.workflow import DefaultWorkflowHandler, WorkflowResult

from app.cache import AnswerCache
from app.charts import PLOTLY_CONFIG
from app.clarify import (
    ClarifyDecision,
    CompanyRow,
    apply_decision,
    clarification_text,
    is_ranking,
    merge_state,
    missing_slots,
)
from app.conversation import ConversationState, load_state, save_state
from app.provenance import provenance_ui_component

if TYPE_CHECKING:
    from vanna.core.agent.agent import Agent
    from vanna.core.user import User

ClarifyFn = Callable[
    [str, ConversationState, Sequence[Message], "User"],
    Awaitable[ClarifyDecision],
]


def replay_components(hit: dict) -> List[UiComponent]:
    components: List[UiComponent] = []
    rows = hit.get("rows") or []
    if rows:
        table = DataFrameComponent.from_records(rows, title="Cached query results")
        components.append(
            UiComponent(
                rich_component=table,
                simple_component=SimpleTextComponent(text="Cached table"),
            )
        )
    chart = hit.get("chart")
    if chart:
        components.append(
            UiComponent(
                rich_component=ChartComponent(
                    chart_type="plotly",
                    data=chart,
                    title=hit.get("title") or "Cached chart",
                    interactive=True,
                    config=dict(PLOTLY_CONFIG),
                ),
                simple_component=SimpleTextComponent(text="Cached chart"),
            )
        )
    markdown = hit.get("markdown") or ""
    if markdown:
        components.append(
            UiComponent(
                rich_component=RichTextComponent(content=markdown, markdown=True),
                simple_component=SimpleTextComponent(text=markdown),
            )
        )
    provenance = hit.get("provenance")
    if provenance:
        components.append(provenance_ui_component(provenance))
    return components


def _append_turn(user_text: str, assistant_text: str):
    async def mutate(conversation: Conversation) -> None:
        conversation.add_message(Message(role="user", content=user_text))
        conversation.add_message(Message(role="assistant", content=assistant_text))

    return mutate


def _save(
    conversation_id: str, state: ConversationState, conversations_dir
) -> None:
    if conversations_dir:
        save_state(conversation_id, state, conversations_dir)
    else:
        save_state(conversation_id, state)


def _skip_question(
    conversation_id: str,
    state: ConversationState,
    conversations_dir,
    user: "User",
    message: str,
    question: str,
) -> WorkflowResult:
    _save(conversation_id, state, conversations_dir)
    user.metadata["conversation_id"] = conversation_id
    user.metadata["slot_line"] = state.prompt_line()
    return WorkflowResult(
        should_skip_llm=True,
        components=[
            UiComponent(
                rich_component=RichTextComponent(content=question, markdown=True),
                simple_component=SimpleTextComponent(text=question),
            )
        ],
        conversation_mutation=_append_turn(message, question),
    )


def _unresolved_slots(state: ConversationState, message: str) -> List[str]:
    still = missing_slots(state, message)
    if is_ranking(message):
        return [slot for slot in still if slot != "company"]
    return still


class StockJarvisWorkflowHandler(DefaultWorkflowHandler):
    def __init__(
        self,
        catalog: Sequence[CompanyRow],
        cache: AnswerCache,
        welcome_message: str,
        conversations_dir=None,
        clarify_fn: Optional[ClarifyFn] = None,
    ):
        super().__init__(welcome_message=welcome_message)
        self.catalog = list(catalog)
        self.cache = cache
        self.conversations_dir = conversations_dir
        self.clarify_fn = clarify_fn

    async def try_handle(
        self, agent: "Agent", user: "User", conversation: Conversation, message: str
    ) -> WorkflowResult:
        base = await super().try_handle(agent, user, conversation, message)
        if base.should_skip_llm:
            return base

        state = (
            load_state(conversation.id, self.conversations_dir)
            if self.conversations_dir
            else load_state(conversation.id)
        )
        merged = merge_state(state, message, self.catalog)
        missing = missing_slots(merged, message)

        if self.clarify_fn is not None and missing:
            try:
                decision = await self.clarify_fn(
                    message, merged, conversation.messages, user
                )
                merged = apply_decision(merged, decision)
                user.metadata["intent"] = decision.intent
                still = _unresolved_slots(merged, message)
                if not decision.ready or still:
                    question = (
                        decision.question
                        if not decision.ready and decision.question
                        else clarification_text((still or missing)[0])
                    )
                    return _skip_question(
                        conversation.id,
                        merged,
                        self.conversations_dir,
                        user,
                        message,
                        question,
                    )
            except Exception:
                return _skip_question(
                    conversation.id,
                    merged,
                    self.conversations_dir,
                    user,
                    message,
                    clarification_text(missing[0]),
                )
        elif missing:
            return _skip_question(
                conversation.id,
                merged,
                self.conversations_dir,
                user,
                message,
                clarification_text(missing[0]),
            )

        _save(conversation.id, merged, self.conversations_dir)
        user.metadata["conversation_id"] = conversation.id
        user.metadata["slot_line"] = merged.prompt_line()

        hit = self.cache.get(message, session_id=conversation.id)
        if hit:
            markdown = hit.get("markdown") or "Cached answer."
            return WorkflowResult(
                should_skip_llm=True,
                components=replay_components(hit),
                conversation_mutation=_append_turn(message, markdown),
            )

        return WorkflowResult(should_skip_llm=False)

