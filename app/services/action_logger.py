"""
KineticSketch — Action Logger for Generative AI Training
Silently records every user drawing operation during the sketch phase.
Writes JSONL (JSON Lines) files: one line per action, ordered chronologically.
"""

import json  # noqa: E402
import logging  # noqa: E402
import threading  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from typing import Dict, Any, Optional  # noqa: E402
from app.paths import ACTION_LOG_DIR as CONFIGURED_ACTION_LOG_DIR

logger = logging.getLogger("KineticSketch.ActionLogger")

ACTION_LOG_DIR = str(CONFIGURED_ACTION_LOG_DIR)
CONFIGURED_ACTION_LOG_DIR.mkdir(parents=True, exist_ok=True)

_write_lock = threading.Lock()


def start_session() -> str:
    """Initialize a new drawing session and return the session ID."""
    session_id = str(uuid.uuid4())
    logger.info("Action logging session started: %s", session_id)
    return session_id


def log_action(action_type: str, data: Dict[str, Any], session_id: Optional[str] = None) -> None:
    """
    Log a single user action.
    
    Action types:
        - add_atom: User placed a new atom {element, x, y, atom_id}
        - delete_atom: User removed an atom {atom_id}
        - move_atom: User dragged an atom {atom_id, old_x, old_y, new_x, new_y}
        - add_bond: User connected two atoms {source_id, target_id, bond_type}
        - delete_bond: User removed a bond {source_id, target_id}
        - change_bond_type: User cycled bond type {source_id, target_id, old_type, new_type}
        - change_element: User changed atom element {atom_id, old_element, new_element}
        - clear_canvas: User cleared the entire canvas {}
        - undo: User undid last action {}
        - redo: User redid an action {}
        - submit_render: User clicked render {smiles, atom_count, bond_count}
    """
    try:
        safe_session_id = str(uuid.UUID(session_id or ""))
    except (ValueError, TypeError, AttributeError):
        logger.warning("Rejected action log with invalid session identifier")
        return
    
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": safe_session_id,
        "action": action_type,
        "data": data,
    }
    
    try:
        filepath = CONFIGURED_ACTION_LOG_DIR / f"session_{safe_session_id}.jsonl"
        with _write_lock, filepath.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception as e:
        logger.debug(f"Action log write error: {e}")


def end_session() -> None:
    """Retained for API compatibility; log writes are stateless."""
    return None
