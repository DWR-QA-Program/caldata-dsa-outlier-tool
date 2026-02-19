#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
exec shiny run --host 0.0.0.0 --port "$PORT" app.py