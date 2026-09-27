#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR/.."

echo ">>> Running Database Migrations (Alembic)..."

if [ -f ".venv/bin/alembic" ]; then
    ALEMBIC_BIN=".venv/bin/alembic"
else
    ALEMBIC_BIN="alembic"
fi

$ALEMBIC_BIN upgrade head
