#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

if command -v npm >/dev/null 2>&1; then
  npm install --prefix frontend
fi

cp -n .env.example .env 2>/dev/null || true
echo "Development environment is ready."
