#!/usr/bin/env bash
# Starts backend (8002) + built frontend (5174), runs the Playwright journey, stops both.
# Usage: ./e2e/run_e2e.sh   (from the project root or anywhere)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python}"
LOGDIR="${LOGDIR:-$(mktemp -d)}"
PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$ROOT/backend"
"$PY" -m scripts.seed
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8002 >"$LOGDIR/backend.log" 2>&1 &
PIDS+=($!)

cd "$ROOT/frontend"
[ -d node_modules ] || npm install >"$LOGDIR/npm.log" 2>&1
npm run build >"$LOGDIR/build.log" 2>&1
node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5174 --strictPort >"$LOGDIR/frontend.log" 2>&1 &
PIDS+=($!)

for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8002/api/health >/dev/null && curl -sf http://127.0.0.1:5174/ >/dev/null; then break; fi
  sleep 1
  [ "$i" = 60 ] && { echo "servers did not start; logs in $LOGDIR"; cat "$LOGDIR"/*.log; exit 1; }
done

cd "$ROOT"
BASE_URL=http://127.0.0.1:5174 "$PY" -m pytest e2e/test_e2e.py -v -p no:cacheprovider "$@"
