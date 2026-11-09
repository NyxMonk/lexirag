#!/usr/bin/env bash
# Start LexiRAG locally on macOS (or Linux): database, API and web app.
# Press Ctrl+C to stop the API and web app. The database container keeps
# running so data is preserved; stop it with `docker compose stop`.
#
#   bash scripts/start.sh
#   bash scripts/start.sh --no-reload
set -euo pipefail

# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

RELOAD="--reload"
for arg in "$@"; do
  case "$arg" in
    --no-reload) RELOAD="" ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) fail "Unknown option: $arg" ;;
  esac
done

printf '\n%sStarting LexiRAG%s\n' "$C_BOLD" "$C_RESET"

step "Checking installation"
[ -f "$ENV_FILE" ] || fail ".env not found." "Run: bash scripts/setup.sh"
[ -x "$VENV_PYTHON" ] || fail "Backend virtual environment not found." "Run: bash scripts/setup.sh"
[ -d "$FRONTEND_DIR/node_modules" ] || fail "Frontend dependencies not installed." "Run: bash scripts/setup.sh"
have npm || fail "npm was not found." "Install Node.js 20 LTS or newer."
ok "Installation found"

load_env
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

for p in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  if port_in_use "$p"; then
    fail "Port $p is already in use by $(port_owner "$p")." "Stop that process, or change BACKEND_PORT / FRONTEND_PORT in .env (update VITE_API_BASE_URL and CORS_ORIGINS to match)."
  fi
done
ok "Ports $BACKEND_PORT and $FRONTEND_PORT are free"

ensure_docker
step "Starting database"
start_database
step "Applying database migrations"
run_migrations

if ! (cd "$BACKEND_DIR" && "$VENV_PYTHON" -m app.cli models-status >/dev/null 2>&1); then
  warn "Retrieval models are not downloaded; uploads will fail to process. Run: bash scripts/setup.sh --download-models"
fi

step "Starting services"
# Job control gives each background job its own process group, so the whole
# tree (uvicorn reloader + worker, npm + vite) can be stopped together.
set -m
(cd "$BACKEND_DIR" && exec "$VENV_PYTHON" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" $RELOAD) &
BACKEND_PID=$!
(cd "$FRONTEND_DIR" && exec npm run dev) &
FRONTEND_PID=$!
set +m

cleanup() {
  trap - INT TERM EXIT
  printf '\n'
  info "Stopping backend and frontend..."
  for pid in "$BACKEND_PID" "$FRONTEND_PID"; do
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  ok "Stopped. The database keeps running; stop it with: docker compose stop"
}
trap cleanup INT TERM EXIT

API_URL="http://localhost:$BACKEND_PORT"
PROBE_HOST="$BACKEND_HOST"; [ "$PROBE_HOST" = "0.0.0.0" ] && PROBE_HOST="127.0.0.1"
ready=0
i=0
while [ $i -lt 60 ]; do
  kill -0 "$BACKEND_PID" 2>/dev/null || break
  if curl -fsS --max-time 5 "http://$PROBE_HOST:$BACKEND_PORT/api/v1/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 0.5
  i=$((i + 1))
done
[ "$ready" -eq 1 ] || fail "The backend did not start." "See the errors above."

printf '\n  %sLexiRAG is running%s\n' "$C_GREEN" "$C_RESET"
printf '  App        http://localhost:%s\n' "$FRONTEND_PORT"
printf '  API        %s\n' "$API_URL"
printf '  API docs   %s/docs\n' "$API_URL"
printf '  %sPress Ctrl+C to stop.%s\n\n' "$C_DIM" "$C_RESET"

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
kill -0 "$BACKEND_PID" 2>/dev/null || warn "The backend stopped."
kill -0 "$FRONTEND_PID" 2>/dev/null || warn "The frontend stopped."
