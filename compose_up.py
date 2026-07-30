#!/usr/bin/env python3
"""Start CASCADE via Docker Compose.

Auto-creates .env from .env.example on first run, injecting a random
FLASK_SECRET_KEY so the value is stable across container restarts. Automatically
verifies and downloads required data files if missing.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


def _ensure_env() -> None:
    """Create .env if absent, then make sure FLASK_SECRET_KEY is set."""
    if not ENV_FILE.exists():
        if ENV_EXAMPLE.exists():
            shutil.copy(ENV_EXAMPLE, ENV_FILE)
            print("Created .env from .env.example", flush=True)
        else:
            ENV_FILE.touch()
            print("Created empty .env", flush=True)

    text = ENV_FILE.read_text()

    # Inject a real secret key if the placeholder or a blank value is present
    key_pattern = re.compile(
        r"^(FLASK_SECRET_KEY\s*=\s*)(replace-with-a-long-random-secret|)$",
        re.MULTILINE,
    )
    if key_pattern.search(text) or "FLASK_SECRET_KEY" not in text:
        new_key = secrets.token_urlsafe(48)
        if "FLASK_SECRET_KEY" in text:
            text = key_pattern.sub(rf"\g<1>{new_key}", text)
        else:
            text += f"\nFLASK_SECRET_KEY={new_key}\n"
        ENV_FILE.write_text(text)
        print("Generated and saved FLASK_SECRET_KEY to .env", flush=True)


def _ensure_directories_and_data() -> None:
    """Ensure host directories exist with correct permissions and data files are present."""
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    (ROOT / "app" / "models").mkdir(parents=True, exist_ok=True)

    try:
        from scripts.download_data import ensure_data_files
        ok = ensure_data_files(verbose=True)
        if not ok:
            print("WARNING: Some data files could not be downloaded automatically.", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"Warning during data check: {exc}", file=sys.stderr, flush=True)


def _wait_for_server(url: str, timeout: float = 90.0) -> bool:
    """Poll server URL until it responds or timeout expires."""
    ready_url = f"{url.rstrip('/')}/health/ready"
    deadline = time.monotonic() + timeout
    print("Waiting for application container to be ready...", flush=True)

    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(ready_url, headers={"User-Agent": "CASCADE-Launcher/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status in (200, 302):
                    return True
        except Exception:
            pass

        # Fallback check on root URL
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CASCADE-Launcher/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status in (200, 302):
                    return True
        except Exception:
            pass

        time.sleep(1.5)

    return False


def _open_browser(url: str) -> None:
    """Open URL in default system browser with fallbacks for WSL and Linux environments."""
    print(f"\nOpening CASCADE in browser at: {url} ...", flush=True)

    # WSL support: check if wslview is present
    wslview = shutil.which("wslview")
    if wslview:
        try:
            subprocess.Popen([wslview, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass

    # Standard python webbrowser module
    try:
        if webbrowser.open(url):
            return
    except Exception:
        pass

    # Linux fallback commands
    for cmd in ["xdg-open", "gio", "x-www-browser", "sensible-browser", "firefox", "google-chrome", "chromium"]:
        bin_path = shutil.which(cmd)
        if bin_path:
            try:
                args = [bin_path, "open", url] if cmd == "gio" else [bin_path, url]
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass


def main() -> None:
    docker = shutil.which("docker")
    if not docker:
        raise SystemExit("docker is not installed or not available on PATH")

    _ensure_env()
    _ensure_directories_and_data()

    # Load .env into the process environment so compose picks it up
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

    from app.runtime import is_port_available, select_available_port

    requested = os.getenv("HOST_PORT")
    port = select_available_port("0.0.0.0", requested=requested, preferred=7860)
    if requested and not is_port_available("0.0.0.0", port):
        raise SystemExit(f"Configured HOST_PORT {port} is already in use")

    os.environ["HOST_PORT"] = str(port)

    command = [docker, "compose", "up", "-d", *sys.argv[1:]]
    subprocess.run(command, check=True)

    url = f"http://localhost:{port}"

    server_ready = _wait_for_server(url, timeout=90.0)

    print("\n" + "=" * 60)
    if server_ready:
        print(f"  CASCADE is running at: {url}")
    else:
        print(f"  CASCADE starting up... access at: {url}")
    print("  To stop:  docker compose down")
    print("=" * 60 + "\n")

    _open_browser(url)


if __name__ == "__main__":
    main()
