#!/bin/bash
# Publik demo av Konsiliet: en separat serverinstans med engångsdatabas och bara syntetisk data.
#
#   drift/publik-demo.sh            bygger webben i demoläge, fyller en ny databas och startar på 127.0.0.1:8795
#   drift/publik-demo.sh --utan-live   utan syntetiska livepunkter var 2:a sekund
#
# Rör aldrig ~/.konsiliet/konsiliet.db och startar ingen tunnel. Vill du visa demon utåt senare:
#   cloudflared tunnel --url http://127.0.0.1:8795
# (en quick tunnel; kör den själv när du vill att sidan ska synas.)
#
# Vad som går att nå utifrån: webben och läsande GET mot demodatan. Inget som startar språkmodellen,
# ingen 1177-hämtning, ingen WebSocket. Se drift/publik_demo.py.
set -euo pipefail

PORT="${KONSILIET_DEMO_PORT:-8795}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LIVE=1
[ "${1:-}" = "--utan-live" ] && LIVE=0

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT är upptagen. Stoppa det som kör där eller sätt KONSILIET_DEMO_PORT." >&2
  exit 1
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/konsiliet-publik-demo.XXXXXX")"
export KONSILIET_DB="$TMP/demo.db"
export KONSILIET_DATORN=0
export KONSILIET_DEVICE_TOKENS=""
echo "Engångsdatabas: $KONSILIET_DB"

echo "Bygger webben i demoläge (web/dist-demo)"
(cd "$REPO/web" && npm run --silent build:demo >/dev/null)

PIDS=()
stada() {
  for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done
  rm -rf "$TMP"
  echo "Demon stoppad, engångsdatabasen raderad."
}
trap stada EXIT INT TERM

cd "$REPO/server"
PYTHONPATH="$REPO/drift" uv run --quiet uvicorn publik_demo:app --host 127.0.0.1 --port "$PORT" --log-level warning &
PIDS+=($!)

for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null || { echo "Servern startade inte." >&2; exit 1; }

echo "Fyller på med 7 dygn syntetisk data (källa dev-syntetisk)"
node "$REPO/web/dev/ingest.mjs" --url "http://127.0.0.1:$PORT" --backfill 168 --once

if [ "$LIVE" = 1 ]; then
  node "$REPO/web/dev/ingest.mjs" --url "http://127.0.0.1:$PORT" --backfill 0 >/dev/null 2>&1 &
  PIDS+=($!)
fi

echo
echo "Publik demo kör på http://127.0.0.1:$PORT  (Ctrl+C stoppar och raderar databasen)"
wait "${PIDS[0]}"
