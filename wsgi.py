#!/usr/bin/env python3
"""Production WSGI entry point for KineticSketch AI."""
from app.main import flask_app as application  # noqa: E402

if __name__ == "__main__":
    application.run()
