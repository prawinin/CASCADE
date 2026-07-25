"""Portable filesystem locations for KineticSketch.

Every path is derived from this installed source tree unless an explicit
environment override is supplied.  Runtime code must not depend on the shell's
current working directory; WSGI servers, Celery workers, containers, and IDEs
are all free to choose a different one.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _environment_path(name: str, default: Path) -> Path:
    raw_value = os.getenv(name)
    path = Path(raw_value).expanduser() if raw_value else default
    return path.resolve(strict=False)


_SOURCE_ROOT = Path(__file__).resolve().parent.parent
# Load the source-tree environment file before resolving any overridable path.
# Explicit process variables retain precedence over values in the file.
load_dotenv(_SOURCE_ROOT / ".env", override=False)
PROJECT_ROOT = _environment_path("KINETICSKETCH_ROOT", _SOURCE_ROOT)

APP_DIR = PROJECT_ROOT / "app"
STATIC_DIR = APP_DIR / "static"
GUI_DIR = APP_DIR / "gui"

DATA_DIR = _environment_path("KINETICSKETCH_DATA_DIR", PROJECT_ROOT / "data")
JOBS_DIR = _environment_path("KINETICSKETCH_JOBS_DIR", PROJECT_ROOT / "jobs")
CACHE_DIR = _environment_path("KINETICSKETCH_CACHE_DIR", PROJECT_ROOT / "scratch")
STATE_DIR = _environment_path("KINETICSKETCH_STATE_DIR", DATA_DIR)

DRUG_DATABASE_PATH = _environment_path(
    "DRUG_DATABASE_PATH", DATA_DIR / "drug_database.sqlite"
)
DRUG_FINGERPRINT_PATH = _environment_path(
    "DRUG_FINGERPRINT_PATH", DATA_DIR / "drug_fingerprints.npz"
)
USERS_DATABASE_PATH = _environment_path("USERS_DATABASE_PATH", STATE_DIR / "users.sqlite")
ACTION_LOG_DIR = _environment_path("ACTION_LOG_DIR", STATE_DIR / "action_logs")
MODEL_WEIGHTS_PATH = _environment_path(
    "MODEL_WEIGHTS_PATH", APP_DIR / "models" / "mdrepo_predictor.pt"
)
PDB_CACHE_DIR = _environment_path("PDB_CACHE_DIR", CACHE_DIR / "pdb_cache")
DOCKING_OUTPUT_DIR = _environment_path(
    "DOCKING_OUTPUT_DIR", CACHE_DIR / "docking_results"
)
GNINA_PATH = _environment_path("GNINA_PATH", PROJECT_ROOT / "gnina")


def ensure_runtime_directories() -> None:
    """Create only mutable runtime directories, never required asset files."""

    for directory in (DATA_DIR, STATE_DIR, JOBS_DIR, CACHE_DIR, ACTION_LOG_DIR, PDB_CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def job_directory(user_id: str, job_id: str) -> Path:
    """Return a canonical job directory contained by the configured jobs root."""

    root = JOBS_DIR.resolve(strict=False)
    candidate = (root / user_id / job_id).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise ValueError("Path traversal detected in job directory construction.")
    return candidate
