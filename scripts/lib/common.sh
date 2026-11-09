# Shared helpers for setup.sh and start.sh.
# Written for the bash 3.2 that ships with macOS (no associative arrays, no `wait -n`).

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
ENV_FILE="$ROOT/.env"
DB_CONTAINER="lexirag-db"

if [ -t 1 ]; then
  C_RESET=$'\033[0m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_DIM=$'\033[90m'; C_BOLD=$'\033[1m'
else
  C_RESET=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_DIM=""; C_BOLD=""
fi

step() { printf '\n%s> %s%s\n' "$C_BOLD" "$1" "$C_RESET"; }
ok()   { printf '  %s[ok]%s   %s\n' "$C_GREEN" "$C_RESET" "$1"; }
info() { printf '  %s[..]   %s%s\n' "$C_DIM" "$1" "$C_RESET"; }
warn() { printf '  %s[warn]%s %s\n' "$C_YELLOW" "$C_RESET" "$1"; }
fail() {
  printf '  %s[fail]%s %s\n' "$C_RED" "$C_RESET" "$1" >&2
  [ -n "${2:-}" ] && printf '         %s%s%s\n' "$C_YELLOW" "$2" "$C_RESET" >&2
  exit 1
}

have() { command -v "$1" >/dev/null 2>&1; }

# Load KEY=VALUE pairs from .env into the environment without executing it as shell code.
load_env() {
  [ -f "$ENV_FILE" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ''|'#'*) continue ;; esac
    key="${line%%=*}"
    value="${line#*=}"
    key="$(printf '%s' "$key" | tr -d '[:space:]')"
    case "$key" in ''|*[!A-Za-z0-9_]*) continue ;; esac
    value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
    # Values already exported in the shell take precedence.
    if [ -z "${!key+x}" ]; then export "$key=$value"; fi
  done < "$ENV_FILE"
}

find_python() {
  for candidate in python3.13 python3 python python3.12; do
    if have "$candidate"; then
      version="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
      if [ "$version" = "3.13" ] || [ "$version" = "3.12" ]; then
        PYTHON_BIN="$(command -v "$candidate")"
        PYTHON_VERSION="$version"
        return 0
      fi
    fi
  done
  return 1
}

port_in_use() {
  if have lsof; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  elif have nc; then
    nc -z 127.0.0.1 "$1" >/dev/null 2>&1
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1
  fi
}

port_owner() {
  if have lsof; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1 " (PID " $2 ")"}'
  fi
}

docker_running() { docker info >/dev/null 2>&1; }

ensure_docker() {
  have docker || fail "Docker is not installed." "Install Docker Desktop for Mac (Apple Silicon or Intel): https://www.docker.com/products/docker-desktop/"
  docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is not available." "Update Docker Desktop to a recent version."
  if docker_running; then ok "Docker engine is running"; return 0; fi

  if [ "$(uname -s)" = "Darwin" ] && [ -d "/Applications/Docker.app" ]; then
    info "Docker engine is not running; starting Docker Desktop..."
    open -a Docker || true
    i=0
    while [ $i -lt 90 ]; do
      sleep 2
      if docker_running; then ok "Docker engine is running"; return 0; fi
      i=$((i + 1))
    done
  fi
  fail "Docker engine is not running." "Start Docker Desktop, wait until it reports 'Engine running', then re-run this script."
}

db_container_running() {
  [ "$(docker inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null)" = "true" ]
}

start_database() {
  local port="${POSTGRES_PORT:-5433}"
  if ! db_container_running && port_in_use "$port"; then
    fail "Port $port is already in use by $(port_owner "$port")." "Set a free POSTGRES_PORT in .env (for example 5434) and re-run."
  fi
  (cd "$ROOT" && docker compose up -d db) || fail "docker compose up failed." "See the Docker output above."

  info "Waiting for PostgreSQL to become healthy..."
  i=0
  while [ $i -lt 60 ]; do
    if [ "$(docker inspect -f '{{.State.Health.Status}}' "$DB_CONTAINER" 2>/dev/null)" = "healthy" ]; then
      ok "PostgreSQL + pgvector is healthy on 127.0.0.1:$port"
      return 0
    fi
    sleep 2
    i=$((i + 1))
  done
  fail "PostgreSQL did not become healthy in time." "Inspect logs with: docker compose logs db"
}

run_migrations() {
  (cd "$BACKEND_DIR" && "$VENV_PYTHON" -m alembic upgrade head) || fail "Database migrations failed." "Check the database credentials in .env."
  ok "Database schema is up to date"
}
