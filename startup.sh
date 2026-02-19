#!/bin/bash
pip install uv
uv sync
uv run shiny dwr/outlier_tool/app.py --host 0.0.0.0 --port {PORT:-8000}