#!/usr/bin/env bash
# First-time (and repeatable) LexiRAG setup for macOS (Apple Silicon and Intel).
# Also works on Linux. Safe to run repeatedly; existing configuration is never overwritten.
#
#   bash scripts/setup.sh                   # full setup
#   bash scripts/setup.sh --download-models # also fetch the retrieval models (~4.5 GB, one time)
#   bash scripts/setup.sh --skip-database   # dependencies only
set -euo pipefail

# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

SKIP_DATABASE=0
DOWNLOAD_MODELS=0
for arg in "$@"; do
  case "$arg" in
    --skip-database) SKIP_DATABASE=1 ;;
    --download-models) DOWNLOAD_MODELS=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) fail "Unknown option: $arg" ;;
  esac
done

printf '\n%sLexiRAG setup%s\n%sProject: %s (%s)%s\n' "$C_BOLD" "$C_RESET" "$C_DIM" "$ROOT" "$(uname -sm)" "$C_RESET"

# ── Prerequisites ────────────────────────────────────────────
step "Checking prerequisites"

find_python || fail "Python 3.13 was not found." "Install it with Homebrew: brew install python@3.13  (or from https://www.python.org/downloads/macos/)"
if [ "$PYTHON_VERSION" != "3.13" ]; then warn "Using Python $PYTHON_VERSION; 3.13 is the supported version."; else ok "Python $PYTHON_VERSION ($PYTHON_BIN)"; fi

have node || fail "Node.js was not found." "Install Node.js 20 LTS or newer: brew install node@20  (or https://nodejs.org/)"
NODE_VERSION="$(node --version | sed 's/^v//')"
[ "${NODE_VERSION%%.*}" -ge 20 ] || fail "Node.js $NODE_VERSION is too old." "Install Node.js 20 LTS or newer."
ok "Node.js $NODE_VERSION"

have npm || fail "npm was not found." "Reinstall Node.js, which includes npm."
ok "npm $(npm --version)"

[ "$SKIP_DATABASE" -eq 1 ] || ensure_docker

# ── Environment configuration ────────────────────────────────
step "Preparing environment configuration"
if [ -f "$ENV_FILE" ]; then
  ok ".env already exists (left unchanged)"
else
  password="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)"
  awk -v pw="$password" '/^POSTGRES_PASSWORD=/ { print "POSTGRES_PASSWORD=" pw; next } { print }' \
    "$ROOT/.env.example" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  ok "Created .env from .env.example with a generated database password"
fi
load_env

storage="${STORAGE_DIR:-storage}"
case "$storage" in /*) ;; *) storage="$ROOT/$storage" ;; esac
mkdir -p "$storage"
ok "Document storage: $storage"

# ── Backend ──────────────────────────────────────────────────
step "Installing backend dependencies"
if [ ! -x "$VENV_PYTHON" ]; then
  info "Creating virtual environment in backend/.venv"
  "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv" || fail "Could not create the Python virtual environment."
else
  ok "Virtual environment exists"
fi
"$VENV_PYTHON" -m pip install --disable-pip-version-check --quiet --upgrade pip
"$VENV_PYTHON" -m pip install --disable-pip-version-check --quiet -r "$BACKEND_DIR/requirements-dev.txt" \
  || fail "pip install failed." "See the pip output above."
ok "Backend dependencies installed"

# ── Frontend ─────────────────────────────────────────────────
step "Installing frontend dependencies"
lock="$FRONTEND_DIR/package-lock.json"
marker="$FRONTEND_DIR/node_modules/.package-lock.json"
if [ -f "$marker" ] && [ -f "$lock" ] && [ ! "$lock" -nt "$marker" ]; then
  ok "node_modules is up to date"
else
  if [ -f "$lock" ]; then
    (cd "$FRONTEND_DIR" && npm ci --no-audit --no-fund) || fail "npm ci failed." "See the npm output above."
  else
    (cd "$FRONTEND_DIR" && npm install --no-audit --no-fund) || fail "npm install failed." "See the npm output above."
  fi
  ok "Frontend dependencies installed"
fi

# ── Database ─────────────────────────────────────────────────
if [ "$SKIP_DATABASE" -eq 1 ]; then
  warn "Skipped database startup and migrations (--skip-database)."
else
  step "Starting database"
  start_database
  step "Applying database migrations"
  run_migrations
fi

step "Checking retrieval models"
if (cd "$BACKEND_DIR" && "$VENV_PYTHON" -m app.cli models-status >/dev/null 2>&1); then
  ok "Embedding and reranker models are available"
elif [ "$DOWNLOAD_MODELS" -eq 1 ]; then
  info "Downloading BAAI/bge-m3 and BAAI/bge-reranker-v2-m3 (about 4.5 GB)..."
  (cd "$BACKEND_DIR" && "$VENV_PYTHON" -m app.cli download-models)     || fail "Model download failed." "Check your internet connection and disk space, then re-run with --download-models."
  ok "Models downloaded"
else
  warn "Models are not downloaded (about 4.5 GB). Re-run with --download-models to enable processing and search."
fi
if have tesseract; then
  ok "Tesseract OCR found (scanned pages can be read)"
else
  warn "Tesseract OCR not found (optional, for scanned PDFs): brew install tesseract tesseract-lang"
fi

printf '\n%sSetup complete.%s\nStart LexiRAG with:  bash scripts/start.sh\n\n' "$C_GREEN" "$C_RESET"
