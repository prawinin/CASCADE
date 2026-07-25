#!/usr/bin/env python3
"""
KineticSketch AI — Unified Launcher

Starts and manages the full application stack:
  1. Redis       — task broker / result backend
  2. Celery      — async HPC worker
  3. Flask       — web server (app/main.py)

If a service is already running it is left untouched.
Everything started by this script is stopped cleanly on exit (Ctrl+C / SIGTERM).

Usage:
    python run.py
    python run.py --no-browser      # skip auto-opening browser
    python run.py --port 8080       # override Flask port
"""

import atexit
import os
import signal
import socket
import subprocess
import sys
import time
import argparse
import webbrowser
from urllib.parse import urlparse

from app.paths import APP_DIR as APP_PATH, PROJECT_ROOT
from app.runtime import select_available_port

# Paths
ROOT_DIR = str(PROJECT_ROOT)
APP_DIR = str(APP_PATH)

#  Defaults 
DEFAULT_HOST       = os.getenv("HOST", "127.0.0.1")
DEFAULT_PORT       = int(os.environ["PORT"]) if os.getenv("PORT") else None
REDIS_URL          = os.getenv("REDIS_URL")
REDIS_STARTUP_WAIT = 5.0   # seconds to wait for Redis to accept connections
FLASK_STARTUP_WAIT = 30.0  # seconds to wait for Flask to be ready
CELERY_CONCURRENCY = int(os.getenv("CELERY_CONCURRENCY", "1"))

#  Process registry 
_procs: dict[str, subprocess.Popen] = {}   # name → process
_we_started: set[str] = set()              # names we launched (not pre-existing)


# 
# Helpers
# 

def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _redis_ping(redis_url: str) -> bool:
    """True if Redis is reachable and responding to PING."""
    try:
        import redis
        return bool(redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1).ping())
    except Exception:
        return False


def _wait_until(fn, timeout: float, interval: float = 0.3) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


def _log(msg: str) -> None:
    print(f"[KineticSketch] {msg}", flush=True)


def _kill(name: str) -> None:
    proc = _procs.pop(name, None)
    if proc is None or name not in _we_started:
        return
    if proc.poll() is not None:
        return
    _log(f"Stopping {name} (PID {proc.pid})…")
    try:
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        _log(f"{name} stopped.")
    except Exception as exc:
        _log(f"Warning stopping {name}: {exc}")


def _shutdown_all() -> None:
    # Shutdown in reverse startup order: Flask → Celery → Redis
    for name in ("flask", "celery", "redis"):
        _kill(name)


def _signal_handler(signum, frame) -> None:
    _shutdown_all()
    sys.exit(0)


# 
# Service starters
# 

def start_redis() -> bool:
    """Ensure Redis is running. Returns True if ready."""
    global REDIS_URL
    if REDIS_URL and _redis_ping(REDIS_URL):
        _log("Redis already running — skipping.")
        return True

    parsed = urlparse(REDIS_URL) if REDIS_URL else None
    if parsed and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        _log("Configured external Redis is unavailable; it will not be started locally.")
        return False

    requested_port = parsed.port if parsed else None
    redis_port = select_available_port("127.0.0.1", requested=requested_port, preferred=6379)
    if requested_port and _port_open("127.0.0.1", redis_port):
        _log(f"ERROR: configured Redis port {redis_port} is occupied by a non-Redis service.")
        return False
    REDIS_URL = f"redis://127.0.0.1:{redis_port}/0"
    os.environ["REDIS_URL"] = REDIS_URL

    redis_bin = _find_binary("redis-server")
    if not redis_bin:
        _log("ERROR: redis-server not found in PATH. Install with: sudo dnf install redis")
        return False

    _log("Starting Redis…")
    proc = subprocess.Popen(
        [redis_bin, "--daemonize", "no",
         "--loglevel", "warning",
         "--port", str(redis_port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _procs["redis"] = proc
    _we_started.add("redis")

    ready = _wait_until(lambda: _redis_ping(REDIS_URL), timeout=REDIS_STARTUP_WAIT)
    if not ready:
        _log("ERROR: Redis did not become ready in time.")
        return False

    _log(f" Redis ready on port {redis_port}")
    return True


def start_celery() -> bool:
    """Start a Celery worker in the background. Returns True on success."""
    celery_bin = _find_binary("celery")
    if not celery_bin:
        # Try via python -m celery
        celery_cmd = [sys.executable, "-m", "celery"]
    else:
        celery_cmd = [celery_bin]

    _log("Starting Celery worker…")
    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT_DIR

    proc = subprocess.Popen(
        celery_cmd + [
            "-A", "app.tasks.celery_app",
            "worker",
            "--loglevel=warning",
            f"--concurrency={max(1, CELERY_CONCURRENCY)}",
            "-n", "kinetic@%h",
        ],
        cwd=ROOT_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _procs["celery"] = proc
    _we_started.add("celery")

    # Give it a moment to connect to Redis
    time.sleep(2.0)
    if proc.poll() is not None:
        _log("ERROR: Celery worker exited immediately — check app/tasks/celery_app.py")
        return False

    _log(f" Celery worker running (PID {proc.pid})")
    return True


def start_flask(host: str, port: int) -> bool:
    """Start the Flask dev server. Returns True when it accepts connections."""
    if not os.path.isfile(os.path.join(APP_DIR, "main.py")):
        _log(f"ERROR: Cannot find the app.main module under {APP_DIR}")
        return False

    env = os.environ.copy()
    env["HOST"] = host
    env["PORT"] = str(port)
    env["FLASK_RUN_WITHOUT_DEBUGGER"] = "1"

    _log(f"Starting Flask server on http://{host}:{port} …")
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=ROOT_DIR,
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    _procs["flask"] = proc
    _we_started.add("flask")

    ready = _wait_until(lambda: _port_open(host, port), timeout=FLASK_STARTUP_WAIT)
    if not ready:
        _log("ERROR: Flask did not start within 30 seconds.")
        return False

    _log(f" Flask ready → http://{'localhost' if host in ('0.0.0.0','') else host}:{port}")
    return True


def _find_binary(name: str) -> str | None:
    """Return full path to binary, or None if not found."""
    import shutil
    return shutil.which(name)


# 
# Main
# 

def main() -> None:
    parser = argparse.ArgumentParser(description="KineticSketch unified launcher")
    parser.add_argument("--host",       default=DEFAULT_HOST)
    parser.add_argument("--port",       type=int, default=DEFAULT_PORT,
                        help="Web port; scans from 7860 when omitted")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-celery",  action="store_true",
                        help="Skip Celery worker (async HPC tasks will be unavailable)")
    args = parser.parse_args()
    explicit_port = args.port is not None
    args.port = select_available_port(args.host, requested=args.port, preferred=7860)

    # Register cleanup
    atexit.register(_shutdown_all)
    signal.signal(signal.SIGINT,  _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    url = f"http://{'localhost' if args.host in ('0.0.0.0', '') else args.host}:{args.port}"

    #  Already fully running? 
    if _port_open("127.0.0.1", args.port):
        if explicit_port:
            _log(f"ERROR: configured web port {args.port} is already in use.")
            sys.exit(1)
        args.port = select_available_port(args.host, preferred=args.port + 1)
        url = f"http://{'localhost' if args.host in ('0.0.0.0', '') else args.host}:{args.port}"

    print()
    print("  ")
    print("          KineticSketch AI             ")
    print("  ")
    print()

    #  1. Redis 
    if not start_redis():
        _log("Continuing without Redis — async HPC tasks will be unavailable.")

    #  2. Celery 
    if not args.no_celery and REDIS_URL and _redis_ping(REDIS_URL):
        if not start_celery():
            _log("Continuing without Celery — async HPC tasks will be unavailable.")
    elif args.no_celery:
        _log("Celery skipped (--no-celery).")
    else:
        _log("Celery skipped — Redis is not available.")

    #  3. Flask 
    if not start_flask(args.host, args.port):
        _shutdown_all()
        sys.exit(1)

    print()
    _log(f"  All services running — open: {url}")
    print()

    #  4. Open browser 
    if not args.no_browser:
        webbrowser.open(url)

    #  5. Wait — block until Flask exits or we're killed 
    flask_proc = _procs.get("flask")
    try:
        if flask_proc:
            flask_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown_all()


if __name__ == "__main__":
    main()
