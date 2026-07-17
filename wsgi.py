#!/usr/bin/env python3
"""Production WSGI entry point for KineticSketch AI."""
import os
import sys

# Resolve absolute paths and add 'app' directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(current_dir, "app")
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from main import flask_app as application

if __name__ == "__main__":
    application.run()
