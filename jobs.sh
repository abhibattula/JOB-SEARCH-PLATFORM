#!/bin/sh
# Headless commands with the project's venv, e.g.:
#   ./jobs.sh refresh        ./jobs.sh refresh --force        ./jobs.sh load-sponsorship
cd "$(dirname "$0")" || exit 1
if [ ! -x ".venv/bin/python" ]; then
    echo "Virtual environment not found. Run setup first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/python -m pip install -r requirements.txt"
    exit 1
fi
exec .venv/bin/python cli.py "$@"
