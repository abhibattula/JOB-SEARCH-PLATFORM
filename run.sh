#!/bin/sh
# Start the Job Engine desktop app using the project's virtual environment.
cd "$(dirname "$0")" || exit 1
if [ ! -x ".venv/bin/python" ]; then
    echo "Virtual environment not found. Run setup first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/python -m pip install -r requirements.txt"
    exit 1
fi
exec .venv/bin/python desktop.py "$@"
