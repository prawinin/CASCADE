#!/bin/bash
set -e

# The Python launcher respects an explicit hosting-provider PORT and selects a
# free local port when PORT is unset. exec keeps the server as PID 1.
exec python serve.py
