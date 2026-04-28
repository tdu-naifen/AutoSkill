"""Track skill proposal accept/reject decisions and adjust threshold progressively."""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILE = Path.home() / ".autoskill" / "proposal_thresholds.json"

DEFAULT_THRESHOLD = 0.85
MIN_THRESHOLD = 0.6
MAX_THRESHOLD = 0.95
HISTORY_WINDOW = 20  # look at last N decisions


def _read_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"threshold": DEFAULT_THRESHOLD, "decisions": []}


def _write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_threshold() -> float:
    """Get current proposal threshold, adjusted by accept/reject history."""
    state = _read_state()
    return state.get("threshold", DEFAULT_THRESHOLD)


def record_decision(proposal_name: str, accepted: bool) -> None:
    """Record an accept/reject decision and recalculate threshold."""
    state = _read_state()
    decisions = state.get("decisions", [])
    decisions.append({"name": proposal_name, "accepted": accepted})

    # Keep only last HISTORY_WINDOW decisions
    decisions = decisions[-HISTORY_WINDOW:]

    # Recalculate threshold
    if len(decisions) >= 5:  # need minimum history
        accept_rate = sum(1 for d in decisions if d["accepted"]) / len(decisions)
        current = state.get("threshold", DEFAULT_THRESHOLD)

        if accept_rate > 0.7:
            # User likes proposals → lower threshold (more proposals)
            new_threshold = max(MIN_THRESHOLD, current - 0.05)
        elif accept_rate < 0.3:
            # User rejects most → raise threshold (fewer proposals)
            new_threshold = min(MAX_THRESHOLD, current + 0.05)
        else:
            new_threshold = current

        state["threshold"] = round(new_threshold, 2)
        logger.info("Threshold adjusted: %.2f → %.2f (accept rate: %.1f%%)",
                    current, new_threshold, accept_rate * 100)

    state["decisions"] = decisions
    _write_state(state)
