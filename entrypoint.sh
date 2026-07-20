#!/bin/bash
set -e

# Port configuration
PORT=${PORT:-7860}
HOST=${HOST:-0.0.0.0}

echo "Starting KineticSketch WSGI production server on ${HOST}:${PORT}..."

# Exec gunicorn as PID 1 for proper Docker signal handling
exec gunicorn --bind "${HOST}:${PORT}" --workers 2 --threads 2 --timeout 120 app.main:flask_app
