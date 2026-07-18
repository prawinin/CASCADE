"""
KineticSketch — Action Logger for Generative AI Training
Silently records every user drawing operation during the sketch phase.
Writes JSONL (JSON Lines) files: one line per action, ordered chronologically.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger("KineticSketch.ActionLogger")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ACTION_LOG_DIR = os.path.join(_PROJECT_ROOT, "data", "action_logs")
os.makedirs(ACTION_LOG_DIR, exist_ok=True)

# Current session log file handle
_session_id: Optional[str] = None
_log_file = None


def start_session() -> str:
    """Initialize a new drawing session and return the session ID."""
    global _session_id, _log_file
    _session_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    filepath = os.path.join(ACTION_LOG_DIR, f"session_{_session_id}.jsonl")
    _log_file = open(filepath, "a")
    logger.info(f"Action logging session started: {_session_id}")
    return _session_id


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
    global _session_id, _log_file
    
    if _log_file is None or _log_file.closed:
        start_session()
    
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id or _session_id,
        "action": action_type,
        "data": data,
    }
    
    try:
        _log_file.write(json.dumps(entry) + "\n")
        _log_file.flush()
    except Exception as e:
        logger.debug(f"Action log write error: {e}")


def end_session() -> None:
    """Close the current logging session."""
    global _log_file
    if _log_file and not _log_file.closed:
        _log_file.close()
    _log_file = None
