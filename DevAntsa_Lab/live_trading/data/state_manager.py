"""
State Manager -- JSON persistence for trading loop state
=========================================================
Saves and loads positions, risk manager state, and last candle times
to a JSON file so the loop can resume after restart.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path

from DevAntsa_Lab.live_trading.config import STATE_FILE

logger = logging.getLogger(__name__)

_state_path = Path(STATE_FILE)


def save_state(
    positions_data: List[Dict[str, Any]],
    risk_state: Dict[str, Any],
    last_candle_times: Dict[str, str],
) -> None:
    """Persist current state to JSON file."""
    state = {
        "positions": positions_data,
        "risk": risk_state,
        "last_candle_times": last_candle_times,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = _state_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2, default=str)
        tmp.replace(_state_path)
    except Exception as e:
        logger.error("Failed to save state: %s", e)


def load_state() -> Optional[Dict[str, Any]]:
    """Load state from JSON file. Returns None if no state file exists."""
    if not _state_path.exists():
        return None
    try:
        with open(_state_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load state: %s", e)
        return None


def serialize_candle_times(candle_times: Dict[str, datetime]) -> Dict[str, str]:
    """Convert {strategy_name: datetime} to {strategy_name: iso_string}."""
    return {k: v.isoformat() for k, v in candle_times.items()}


def deserialize_candle_times(data: Dict[str, str]) -> Dict[str, datetime]:
    """Convert {strategy_name: iso_string} to {strategy_name: datetime}."""
    result: Dict[str, datetime] = {}
    for k, v in data.items():
        try:
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            result[k] = dt
        except (ValueError, TypeError):
            continue
    return result
