#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR/.."

echo ">>> Starting Personal Job Intelligence Platform (Development)..."

if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="python"
fi

$PYTHON_BIN -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
