#!/usr/bin/env python3
"""
Hugging Face Spaces Entrypoint (Gradio SDK Workaround)
Starts local Redis-server, Celery worker, and binds Flask app to port 7860.
"""
import subprocess  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

print("--- STARTING SYSTEM SERVICES FOR KINETIC_SKETCH ---", flush=True)

# 1. Start Redis in the background
print("Starting local Redis server...", flush=True)
try:
    # Run redis-server as a daemon
    subprocess.Popen(["redis-server", "--daemonize", "yes"])
    time.sleep(2)  # Give Redis a moment to bind and start
    print("Redis server started successfully.", flush=True)
except Exception as e:
    print(f"WARNING: Failed to start Redis server: {e}", flush=True)

# 2. Start Celery worker in the background
print("Starting Celery worker...", flush=True)
try:
    env = os.environ.copy()
    env["REDIS_URL"] = "redis://localhost:6379/0"
    
    # Start celery worker asynchronously
    subprocess.Popen(
        [sys.executable, "-m", "celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info", "--concurrency=1"],
        env=env
    )
    print("Celery worker started successfully.", flush=True)
except Exception as e:
    print(f"WARNING: Failed to start Celery worker: {e}", flush=True)

# 3. Configure environment variables for the main application
print("Configuring application environment...", flush=True)
os.environ["PORT"] = "7860"  # Hugging Face routes port 7860 to the web
os.environ["HOST"] = "0.0.0.0"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

# 4. Launch the application
print("Launching KineticSketch server...", flush=True)
import runpy  # noqa: E402
runpy.run_path("kinetic_sketch.py", run_name="__main__")
