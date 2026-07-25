#!/usr/bin/env python3
"""Portable production launcher for the KineticSketch Gunicorn server."""

from __future__ import annotations

import os
import sys

from app.paths import PROJECT_ROOT
from app.runtime import is_port_available, select_available_port


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer, got {raw_value!r}") from exc
    if value < 1:
        raise SystemExit(f"{name} must be at least 1, got {value}")
    return value


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0").strip() or "0.0.0.0"
    explicit_port = os.getenv("PORT")
    port = select_available_port(host, requested=explicit_port, preferred=7860)

    if explicit_port and not is_port_available(host, port):
        raise SystemExit(
            f"Configured port {port} is already in use. Hosting-provider PORT values "
            "cannot be changed automatically; stop the conflicting process or change PORT."
        )

    os.environ["HOST"] = host
    os.environ["PORT"] = str(port)
    workers = _positive_int("WEB_CONCURRENCY", 1)
    threads = _positive_int("GUNICORN_THREADS", 2)
    timeout = _positive_int("GUNICORN_TIMEOUT", 120)

    command = [
        sys.executable,
        "-m", "gunicorn",
        "--bind", f"{host}:{port}",
        "--workers", str(workers),
        "--threads", str(threads),
        "--timeout", str(timeout),
        "--worker-tmp-dir", "/tmp",
        "--no-control-socket",
        "--chdir", str(PROJECT_ROOT),
        "--access-logfile", "-",
        "--error-logfile", "-",
        "app.main:flask_app",
    ]
    print(
        f"Starting KineticSketch on {host}:{port} "
        f"({workers} worker(s), {threads} thread(s) each)",
        flush=True,
    )
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
