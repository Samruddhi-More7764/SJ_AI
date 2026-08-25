from pathlib import Path

from app.conversation import ConversationState, load_state, save_state


def test_state_roundtrip(tmp_path: Path):
    state = ConversationState(
        companies=["SBIN"], metrics=["revenue"], period="Q1 2018"
    )
    save_state("conv-1", state, tmp_path)
    loaded = load_state("conv-1", tmp_path)
    assert loaded.companies == ["SBIN"]
    assert loaded.metrics == ["revenue"]
    assert loaded.period == "Q1 2018"
    assert "SBIN" in loaded.prompt_line()


def test_missing_state_is_empty(tmp_path: Path):
    loaded = load_state("unknown", tmp_path)
    assert loaded.companies == []
    assert loaded.period is None
