"""Same-thread conversation slots (company, metric, period, basis)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

CONVERSATIONS_DIR = Path("./conversations")


@dataclass
class ConversationState:
    companies: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    period: Optional[str] = None
    basis: Optional[str] = None

    def prompt_line(self) -> str:
        bits = []
        if self.companies:
            bits.append("companies=" + ", ".join(self.companies))
        if self.metrics:
            bits.append("metrics=" + ", ".join(self.metrics))
        if self.period:
            bits.append(f"period={self.period}")
        if self.basis:
            bits.append(f"basis={self.basis}")
        if not bits:
            return "Conversation context: (none yet). Follow-ups inherit slots once set."
        return (
            "Conversation context: "
            + "; ".join(bits)
            + ". Follow-ups inherit these slots unless the user replaces them."
        )


def _state_path(conversation_id: str, base_dir: Path = CONVERSATIONS_DIR) -> Path:
    return Path(base_dir) / conversation_id / "state.json"


def load_state(
    conversation_id: str, base_dir: Path = CONVERSATIONS_DIR
) -> ConversationState:
    path = _state_path(conversation_id, base_dir)
    if not path.exists():
        return ConversationState()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return ConversationState()
    return ConversationState(
        companies=list(data.get("companies") or []),
        metrics=list(data.get("metrics") or []),
        period=data.get("period"),
        basis=data.get("basis"),
    )


def save_state(
    conversation_id: str,
    state: ConversationState,
    base_dir: Path = CONVERSATIONS_DIR,
) -> None:
    path = _state_path(conversation_id, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2))
