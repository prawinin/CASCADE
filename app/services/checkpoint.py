import os
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger("KineticSketch.Checkpoint")

class CheckpointManager:
    """
    Manages live workspace state checkpointing.
    Writes transitions sequentially to workspace_progress.json.
    Prevents execution cut-offs and enables secondary models to resume compilation.
    """
    def __init__(self, filepath: str = "workspace_progress.json"):
        self.filepath = filepath
        self.state = self.load_checkpoint()

    def load_checkpoint(self) -> Dict[str, Any]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    data = json.load(f)
                    logger.info(f"Loaded active state checkpoint from {self.filepath}")
                    return data
            except Exception as e:
                logger.error(f"Failed to read checkpoint file: {e}. Re-initializing.")
        
        return {
            "current_phase": "INIT",
            "phases_completed": [],
            "data": {},
            "timestamp": datetime.now().isoformat()
        }

    def save_checkpoint(self, phase: str, data_updates: Optional[Dict[str, Any]] = None):
        self.state["current_phase"] = phase
        if phase not in self.state["phases_completed"] and phase != "INIT":
            self.state["phases_completed"].append(phase)
        if data_updates:
            self.state["data"].update(data_updates)
        self.state["timestamp"] = datetime.now().isoformat()

        try:
            with open(self.filepath, "w") as f:
                json.dump(self.state, f, indent=4)
            logger.info(f"Checkpoint successfully written: Phase {phase}")
        except Exception as e:
            logger.error(f"Failed to write state checkpoint to disk: {e}")

    def is_phase_completed(self, phase: str) -> bool:
        return phase in self.state["phases_completed"]

    def get_data(self, key: str, default: Any = None) -> Any:
        return self.state["data"].get(key, default)
