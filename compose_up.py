#!/usr/bin/env python3
"""Start CASCADE via Docker Compose.

Auto-creates .env from .env.example on first run, injecting a random
FLASK_SECRET_KEY so the value is stable across container restarts.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


def _ensure_env() -> None:
    """Create .env if absent, then make sure FLASK_SECRET_KEY is set."""
    if not ENV_FILE.exists():
        if ENV_EXAMPLE.exists():
            shutil.copy(ENV_EXAMPLE, ENV_FILE)
            print(f"Created .env from .env.example")
        else:
            ENV_FILE.touch()
            print("Created empty .env")

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
        print("Generated and saved FLASK_SECRET_KEY to .env")


def main() -> None:
    docker = shutil.which("docker")
    if not docker:
        raise SystemExit("docker is not installed or not available on PATH")

    _ensure_env()

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

    import time
    import webbrowser

    url = f"http://localhost:{port}"
    print(f"\nCASCADE is running at {url}")
    print("\n" + "=" * 50)
    print("  To stop:  docker compose down")
    print("=" * 50 + "\n")

    time.sleep(2)
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == "__main__":
    main()

