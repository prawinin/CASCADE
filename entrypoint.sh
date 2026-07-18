#!/bin/bash
# 1. Start Redis in the background
redis-server --daemonize yes

# 2. Start Celery worker in the background
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=1 &

# 3. Start the Flask App on port 7860 (Hugging Face expects port 7860)
export PORT=7860
export HOST=0.0.0.0
export REDIS_URL=redis://localhost:6379/0

python kinetic_sketch.py
