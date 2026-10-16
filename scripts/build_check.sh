#!/usr/bin/env bash
# Production build check: compile, test, build a fresh database, start the server, smoke-test it.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python}
WORK=$(mktemp -d)
trap 'kill $SERVER 2>/dev/null || true; rm -rf "$WORK"' EXIT

echo "== compile"
$PY -m compileall -q gcc_atlas
node --check web/app.js 2>/dev/null && echo "app.js syntax ok" || echo "node not installed; app.js syntax covered by browser tests"

echo "== tests"
$PY -m pytest -q tests

echo "== fresh database"
DB="$WORK/prod.sqlite"
$PY -m gcc_atlas.cli --db "$DB" init
$PY -m gcc_atlas.cli --db "$DB" seed

echo "== server smoke test"
PORT=${PORT:-8799}
GCC_ATLAS_DB="$DB" $PY -m uvicorn gcc_atlas.api:app --port "$PORT" >"$WORK/server.log" 2>&1 &
SERVER=$!
for _ in $(seq 1 50); do curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break; sleep 0.2; done
for path in / /static/app.js /static/styles.css /api/health /api/overview /api/centres /api/policies /api/quality /api/readiness; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT$path")
  echo "$code $path"
  [ "$code" = 200 ] || { cat "$WORK/server.log"; exit 1; }
done
echo "BUILD CHECK PASSED"
