#!/usr/bin/env python3
"""
KineticSketch AI - Root Launcher
Allows booting the application seamlessly from the root workspace directory.
"""
import os
import sys
import runpy

# Resolve absolute paths to prevent launch system conflicts
current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(current_dir, "app")

if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

if __name__ == "__main__":
    # Boot the Taipy main module
    main_script_path = os.path.join(app_dir, "main.py")
    runpy.run_path(main_script_path, run_name="__main__")
