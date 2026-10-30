#!/usr/bin/env bash
# Start the 40Ksim backend (FastAPI, :8000) and frontend (Vite, :5173).
#
#   ./dev.sh              set up if needed, then run both
#   ./dev.sh backend      backend only
#   ./dev.sh frontend     frontend only
#   ./dev.sh test         run the backend test suite
#   ./dev.sh setup        install dependencies and exit
#
# Ctrl+C stops everything. The client calls http://127.0.0.1:8000, so the
# backend port is fixed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/venv"
BACKEND_PORT=8000
PY="${PYTHON:-python3}"

say() { printf '\033[1;36m[dev]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[dev]\033[0m %s\n' "$*" >&2; exit 1; }

setup_backend() {
  command -v "$PY" >/dev/null || die "python3 not found (set PYTHON=/path/to/python)"
  if [ ! -x "$VENV/bin/python" ]; then
    say "Creating Python virtualenv in venv/"
    "$PY" -m venv "$VENV"
  fi
  local reqs="$ROOT/roster_creator/requirements.txt"
  local stamp="$VENV/.requirements-installed"
  if [ ! -f "$stamp" ] || [ "$reqs" -nt "$stamp" ]; then
    say "Installing backend dependencies"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install --quiet -r "$reqs"
    touch "$stamp"
  fi
  if [ ! -f "$ROOT/data-schema/factions/faction_metadata.json" ]; then
    say "Note: data-schema/factions/faction_metadata.json is missing, so faction"
    say "      selection will fail. Run scripts/generate_lore.py or restore the file."
  fi
  if [ ! -f "${FORTYK_MCP_SERVER_DIR:-$HOME/40k-mcp-server}/build/index.js" ]; then
    say "Note: 40k MCP server not found (looked in \${FORTYK_MCP_SERVER_DIR:-~/40k-mcp-server})."
    say "      Roster building works; Codex rules text will be unavailable."
  fi
}

setup_frontend() {
  command -v npm >/dev/null || die "npm not found (install Node.js 20+)"
  if [ ! -d "$ROOT/client/node_modules" ]; then
    say "Installing frontend dependencies"
    npm --prefix "$ROOT/client" install
  fi
}

run_backend() {
  say "Backend  -> http://127.0.0.1:$BACKEND_PORT  (docs: /docs)"
  cd "$ROOT"
  exec "$VENV/bin/python" -m uvicorn roster_creator.api:app \
    --app-dir "$ROOT/roster_creator/src" \
    --host 127.0.0.1 --port "$BACKEND_PORT" --reload
}

run_frontend() {
  say "Frontend -> http://localhost:5173"
  exec npm --prefix "$ROOT/client" run dev
}

run_both() {
  # Job control gives each server its own process group, so Ctrl+C can stop
  # uvicorn's reloader and Vite's child processes too.
  set -m
  run_backend & BACK=$!
  run_frontend & FRONT=$!
  trap 'say "Shutting down"; kill -TERM -- -"$BACK" -"$FRONT" 2>/dev/null || true' INT TERM
  trap 'kill -TERM -- -"$BACK" -"$FRONT" 2>/dev/null || true' EXIT
  # Exit as soon as either server dies so a crash is not hidden.
  wait -n "$BACK" "$FRONT" || true
}

case "${1:-both}" in
  setup)    setup_backend; setup_frontend; say "Setup complete." ;;
  backend)  setup_backend; run_backend ;;
  frontend) setup_frontend; run_frontend ;;
  test)     setup_backend; cd "$ROOT/roster_creator"; exec "$VENV/bin/python" -m pytest -q "${@:2}" ;;
  both)     setup_backend; setup_frontend; run_both ;;
  *)        die "Unknown command '$1'. Use: both | backend | frontend | test | setup" ;;
esac
