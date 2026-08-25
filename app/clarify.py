"""Detect missing company / metric / period slots for filings questions."""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

from app.conversation import ConversationState

CompanyRow = Tuple[str, str]

KNOWN_METRICS = {
    "revenue": "revenue",
    "sales": "revenue",
    "turnover": "revenue",
    "income": "total_income",
    "total income": "total_income",
    "other income": "other_income",
    "profit": "profit_after_tax",
    "pat": "profit_after_tax",
    "profit after tax": "profit_after_tax",
    "profit_after_tax": "profit_after_tax",
    "pbt": "profit_before_tax",
    "profit before tax": "profit_before_tax",
    "profit_before_tax": "profit_before_tax",
    "eps": "eps",
    "earnings": "eps",
    "expenses": "expenses",
    "finance costs": "finance_costs",
    "finance_costs": "finance_costs",
    "interest": "interest_earned",
    "interest earned": "interest_earned",
    "interest_earned": "interest_earned",
    "gnpa": "gnpa",
    "nnpa": "nnpa",
}

_PERIOD = re.compile(
    r"\b(?:Q[1-4]|FY\s*\d{2,4}|20\d{2}|latest|current|ytd|annual|"
    r"quarter(?:ly)?|half[\s-]?year(?:ly)?|last\s+quarter)\b",
    re.IGNORECASE,
)

_EXPLORATORY = (
    "list ",
    "which companies",
    "how many companies",
    "company names",
    "symbols from",
    "what tables",
    "schema",
)

_RANKING = re.compile(
    r"\b(?:top|bottom)\s+\d+\b|"
    r"\b(?:highest|lowest|largest|smallest)\b.{0,40}\bcompan|"
    r"\bcompan\w+\s+by\b|"
    r"\brank(?:ing|ed)?\b|"
    r"\bcompare\s+companies\b",
    re.IGNORECASE,
)


def is_exploratory(message: str) -> bool:
    lower = (message or "").lower()
    if extract_metric(lower):
        return False
    return any(hint in lower for hint in _EXPLORATORY)


def is_ranking(message: str) -> bool:
    return bool(_RANKING.search(message or ""))


def extract_metric(message: str) -> Optional[str]:
    lower = (message or "").lower()
    for alias in sorted(KNOWN_METRICS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            return KNOWN_METRICS[alias]
    return None


def extract_period(message: str) -> Optional[str]:
    match = _PERIOD.search(message or "")
    return match.group(0).strip() if match else None


def extract_companies(
    message: str, catalog: Sequence[CompanyRow]
) -> List[str]:
    lower = (message or "").lower()
    found: List[str] = []
    for name, symbol in catalog:
        symbol_l = (symbol or "").lower()
        name_l = (name or "").lower()
        if symbol_l and re.search(rf"\b{re.escape(symbol_l)}\b", lower):
            found.append(symbol)
            continue
        if name_l and name_l in lower:
            found.append(symbol or name)
    return found


def merge_state(
    state: ConversationState,
    message: str,
    catalog: Sequence[CompanyRow],
) -> ConversationState:
    companies = extract_companies(message, catalog) or list(state.companies)
    metric = extract_metric(message)
    metrics = [metric] if metric else list(state.metrics)
    period = extract_period(message) or state.period
    basis = state.basis
    lower = (message or "").lower()
    if "consolidated" in lower and "non-consolidated" not in lower:
        basis = "Consolidated"
    elif "standalone" in lower or "non-consolidated" in lower:
        basis = "Non-Consolidated"
    return ConversationState(
        companies=companies, metrics=metrics, period=period, basis=basis
    )


def missing_slots(
    state: ConversationState, message: str
) -> List[str]:
    if is_exploratory(message) and not state.metrics and not extract_metric(message):
        return []
    if is_ranking(message) and not state.companies:
        return [] if (state.metrics or extract_metric(message)) else ["metric"]
    if not is_fact_question(message, state):
        return []
    missing: List[str] = []
    if not state.companies:
        missing.append("company")
    if not state.metrics:
        missing.append("metric")
    if not state.period:
        missing.append("period")
    return missing


def is_fact_question(message: str, state: ConversationState) -> bool:
    return bool(extract_metric(message) or state.metrics)


def clarification_text(slot: str) -> str:
    if slot == "company":
        return (
            "Which company should I use? Please give an NSE name or symbol "
            "(for example SBIN or State Bank of India)."
        )
    if slot == "metric":
        return (
            "Which metric? For example revenue, profit_after_tax, eps, "
            "or interest_earned."
        )
    return (
        "Which period? For example Q1 2018, FY2018, 2018-06-30, or latest."
    )


def load_company_catalog(database_url: str) -> List[CompanyRow]:
    import psycopg2

    conn = psycopg2.connect(database_url)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT company_name, symbol FROM companies "
            "WHERE company_name IS NOT NULL ORDER BY company_name"
        )
        rows = [(str(name), str(symbol or "")) for name, symbol in cursor.fetchall()]
        cursor.close()
        return rows
    finally:
        conn.close()


CLARIFY_SYSTEM = """You are the clarification step for StockJarvis, a filings-only financial chatbot.
Reply with ONLY a JSON object, no markdown, no extra text:
{
  "ready": true or false,
  "intent": "ranking" | "time_series" | "single_fact" | "exploratory",
  "companies": ["NSE_SYMBOL"],
  "metrics": ["revenue"],
  "period": "latest" or a period string or null,
  "basis": "Consolidated" | "Non-Consolidated" | null,
  "question": "one clarifying question or null"
}

Rules:
- ranking (top N, compare many companies) does NOT need a company. It needs a metric. Period may be "latest".
- Only use ranking when the user asked for top/bottom N, highest/lowest companies, or to compare companies.
- "show revenue" or any metric without a named company is single_fact: ready=false, ask which NSE company or symbol.
- exploratory (list companies, schema) is ready with empty slots.
- single_fact or time_series need a company and a metric. If period is missing, use "latest" when the user said latest/recent, otherwise ask for a period.
- Ask at most one question. Do not invent figures. Do not write SQL.
- Use conversation slots when the user says "that company" or "same metric".
"""


@dataclass
class ClarifyDecision:
    ready: bool
    intent: str = "single_fact"
    companies: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    period: Optional[str] = None
    basis: Optional[str] = None
    question: Optional[str] = None


def parse_clarify_json(raw: str) -> ClarifyDecision:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in clarify response")
    data = json.loads(text[start : end + 1])
    return ClarifyDecision(
        ready=bool(data.get("ready")),
        intent=str(data.get("intent") or "single_fact"),
        companies=[str(c) for c in (data.get("companies") or []) if c],
        metrics=[str(m) for m in (data.get("metrics") or []) if m],
        period=data.get("period"),
        basis=data.get("basis"),
        question=(data.get("question") or None),
    )


def apply_decision(
    state: ConversationState, decision: ClarifyDecision
) -> ConversationState:
    return ConversationState(
        companies=decision.companies or list(state.companies),
        metrics=decision.metrics or list(state.metrics),
        period=decision.period or state.period,
        basis=decision.basis or state.basis,
    )


async def ask_clarify(
    llm: Any,
    message: str,
    state: ConversationState,
    history: Sequence[Any],
    user: Any,
) -> ClarifyDecision:
    from vanna.core.llm import LlmMessage, LlmRequest

    bits = []
    for item in list(history)[-8:]:
        role = getattr(item, "role", None)
        content = getattr(item, "content", None)
        if role and content:
            bits.append(f"{role}: {content}")
    user_blob = (
        f"{state.prompt_line()}\n"
        + ("Recent turns:\n" + "\n".join(bits) + "\n" if bits else "")
        + f"User: {message}"
    )
    request = LlmRequest(
        messages=[LlmMessage(role="user", content=user_blob)],
        user=user,
        tools=None,
        temperature=0.2,
        max_tokens=400,
        system_prompt=CLARIFY_SYSTEM,
    )
    response = await llm.send_request(request)
    return parse_clarify_json(response.content or "")

