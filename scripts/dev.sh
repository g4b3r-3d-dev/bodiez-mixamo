#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/backend/.venv"

if [[ ! -x "$VENV/bin/uvicorn" ]]; then
  echo "Ambiente Python não encontrado. Execute ./scripts/install.sh primeiro." >&2
  exit 1
fi
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "Dependências do frontend não encontradas. Execute ./scripts/install.sh primeiro." >&2
  exit 1
fi

cleanup() {
  [[ -n "${BACK_PID:-}" ]] && kill "$BACK_PID" 2>/dev/null || true
  [[ -n "${FRONT_PID:-}" ]] && kill "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$ROOT/backend"
"$VENV/bin/uvicorn" app.stage4_main:app --host 127.0.0.1 --port 8000 &
BACK_PID=$!

cd "$ROOT/frontend"
npm run dev &
FRONT_PID=$!

echo
echo "Bodiez Local iniciado:"
echo "  Frontend: http://127.0.0.1:5173"
echo "  Backend:  http://127.0.0.1:8000"
echo "Pressione Ctrl+C para encerrar."

wait -n "$BACK_PID" "$FRONT_PID"
