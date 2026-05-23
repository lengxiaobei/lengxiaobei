#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
fi

HOST="${BACKEND_HOST:-127.0.0.1}"
PORT="${BACKEND_PORT:-8000}"

exec python3 -m uvicorn backend.main:app --reload --host "$HOST" --port "$PORT"
