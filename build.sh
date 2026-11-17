#!/bin/sh
# One-command rebuild. Uses the project venv when present.
# Default: local preview links for http://127.0.0.1:8080/
# Production (GitHub Pages): ./build.sh --prod
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python build.py "$@"
fi
exec python3 build.py "$@"
