#!/usr/bin/env python3
"""Start Docker Compose on an available loopback host port."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from app.runtime import is_port_available, select_available_port


def main() -> None:
    docker = shutil.which("docker")
    if not docker:
        raise SystemExit("docker is not installed or not available on PATH")

    requested = os.getenv("HOST_PORT")
    port = select_available_port("127.0.0.1", requested=requested, preferred=7860)
    if requested and not is_port_available("127.0.0.1", port):
        raise SystemExit(f"Configured HOST_PORT {port} is already in use")

    import secrets
    environment = os.environ.copy()
    environment["HOST_PORT"] = str(port)
    if "FLASK_SECRET_KEY" not in environment:
        environment["FLASK_SECRET_KEY"] = secrets.token_urlsafe(32)
    
    command = [docker, "compose", "up", "-d", *sys.argv[1:]]
    subprocess.run(command, env=environment, check=True)
    
    import webbrowser
    import time
    
    url = f"http://127.0.0.1:{port}"
    print(f"CASCADE is published locally at {url}")
    
    print("\n" + "="*55)
    print(" 🛑 TO STOP THE CASCADE SERVER, RUN THE COMMAND:")
    print("    docker compose down")
    print("="*55 + "\n")
    
    print("Opening in default browser...")
    
    # Give the web container a moment to start up
    time.sleep(2)
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == "__main__":
    main()
