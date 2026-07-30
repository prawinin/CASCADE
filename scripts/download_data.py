#!/usr/bin/env python3
"""
CASCADE — Data & Model Auto-Downloader
Downloads required database and model files from GitHub Releases if missing.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
from pathlib import Path

RELEASE_BASE = "https://github.com/prawinin/CASCADE/releases/download/v1.0.0"

# Target files relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

FILES_TO_DOWNLOAD = [
    {
        "name": "drug_database.sqlite",
        "url": f"{RELEASE_BASE}/drug_database.sqlite",
        "dest": PROJECT_ROOT / "data" / "drug_database.sqlite",
        "min_size": 100 * 1024 * 1024,  # ~450MB expected
    },
    {
        "name": "drug_fingerprints.npz",
        "url": f"{RELEASE_BASE}/drug_fingerprints.npz",
        "dest": PROJECT_ROOT / "data" / "drug_fingerprints.npz",
        "min_size": 50 * 1024 * 1024,   # ~160MB expected
    },
    {
        "name": "mdrepo_predictor.pt",
        "url": f"{RELEASE_BASE}/mdrepo_predictor.pt",
        "dest": PROJECT_ROOT / "app" / "models" / "mdrepo_predictor.pt",
        "min_size": 4 * 1024 * 1024,    # ~4.8MB expected
    },

]


def _format_size(size_bytes: int | float) -> str:
    """Format bytes to human-readable string."""
    val = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(val) < 1024.0:
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024.0
    return f"{val:.1f} TB"



def _download_with_progress(url: str, dest: Path, name: str) -> None:
    """Download a file with a terminal progress bar, saving to .tmp before atomic rename."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.with_suffix(dest.suffix + ".tmp")

    print(f"[setup] Downloading {name} ...", flush=True)

    start_time = time.time()
    last_print = 0.0

    def progress_callback(blocks_transferred: int, block_size: int, total_size: int) -> None:
        nonlocal last_print
        now = time.time()
        # Limit progress print updates to ~10 per second
        if now - last_print < 0.1 and blocks_transferred * block_size < total_size:
            return
        last_print = now

        downloaded = blocks_transferred * block_size
        if total_size > 0:
            pct = min(100.0, (downloaded / total_size) * 100)
            bar_len = 30
            filled = int(bar_len * downloaded // total_size)
            bar = "=" * filled + ">" + " " * (bar_len - filled - 1) if filled < bar_len else "=" * bar_len
            speed = downloaded / (now - start_time + 1e-5)
            print(
                f"\r[setup] [{bar}] {pct:5.1f}% ({_format_size(downloaded)} / {_format_size(total_size)}) @ {_format_size(speed)}/s",
                end="",
                flush=True,
            )
        else:
            print(f"\r[setup] Downloaded {_format_size(downloaded)}", end="", flush=True)

    try:
        urllib.request.urlretrieve(url, str(tmp_dest), reporthook=progress_callback)
        print(flush=True)
        tmp_dest.replace(dest)
        print(f"[setup] Saved: {dest.relative_to(PROJECT_ROOT)}", flush=True)
    except Exception as exc:
        print(flush=True)
        if tmp_dest.exists():
            try:
                tmp_dest.unlink()
            except OSError:
                pass
        raise RuntimeError(f"Failed to download {name} from {url}: {exc}") from exc


def ensure_data_files(verbose: bool = True) -> bool:
    """Ensure all required data and model files exist and are valid.
    
    Downloads any missing files automatically.
    Returns True if all files are ready.
    """
    all_ok = True
    for item in FILES_TO_DOWNLOAD:
        dest: Path = item["dest"]
        name: str = item["name"]
        min_size: int = item["min_size"]

        # Ensure parent directory exists before anything else
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists() and dest.stat().st_size >= min_size:
            if verbose:
                print(f"[setup] Already exists: {dest.relative_to(PROJECT_ROOT)} ({_format_size(dest.stat().st_size)})", flush=True)
            continue

        if dest.exists() and dest.stat().st_size < min_size:
            print(f"[setup] Incomplete file found for {name} ({dest.stat().st_size} bytes). Re-downloading...", flush=True)
            try:
                dest.unlink()
            except OSError:
                pass

        try:
            _download_with_progress(item["url"], dest, name)
        except Exception as exc:
            print(f"[setup] ERROR: {exc}", file=sys.stderr, flush=True)
            all_ok = False

    return all_ok


if __name__ == "__main__":
    print("[setup] Checking required CASCADE data files...", flush=True)
    success = ensure_data_files()
    if not success:
        print("[setup] WARNING: One or more data files failed to download.", file=sys.stderr, flush=True)
        sys.exit(1)
    print("[setup] All data files ready.", flush=True)
