#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 -m venv "$ROOT/backend/.venv"
"$ROOT/backend/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"

cd "$ROOT/frontend"
npm install

echo
echo "Instalação concluída."
echo "Use ./scripts/dev.sh para iniciar backend e frontend."
