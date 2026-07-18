#!/bin/sh
# macOS double-clickable launcher for the Job Engine desktop app.
cd "$(dirname "$0")" || exit 1
exec ./run.sh "$@"
