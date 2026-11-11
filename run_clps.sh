#!/usr/bin/env bash
# CLPS Luna Browser — One-Command macOS Local Development Launcher
# Manages prerequisite validation, PostgreSQL/Ollama checks, FastAPI backend,
# SPICE+DEM simulation worker, and Express 5 SSR frontend without creating extra files.

set -euo pipefail

# ---------------------------------------------------------------------------
# Path & runtime resolution (POSIX/Bash 3.2 safe, works from any CWD)
# ---------------------------------------------------------------------------
SOURCE_PATH="${BASH_SOURCE[0]}"
while [ -L "$SOURCE_PATH" ]; do
  LINK_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd -P)"
  SOURCE_PATH="$(readlink "$SOURCE_PATH")"
  case "$SOURCE_PATH" in
    /*) ;;
    *) SOURCE_PATH="$LINK_DIR/$SOURCE_PATH" ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd -P)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
ENV_FILE="$BACKEND_DIR/.env"

BASE_TMP="${TMPDIR:-/tmp}"
BASE_TMP="${BASE_TMP%/}"
RUNTIME_DIR="$BASE_TMP/clps-luna-browser-$(id -u)"
LOG_DIR="$RUNTIME_DIR/logs"
PID_FILE="$RUNTIME_DIR/pids.state"
META_FILE="$RUNTIME_DIR/meta.env"
LOCK_DIR="$RUNTIME_DIR/launcher.lock"

# Runtime configuration defaults (overridden cleanly from env or Pydantic Settings)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-clps_luna}"
OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b}"
USER_SUPPLIED_BACKEND_PORT="${BACKEND_PORT:-}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
SSR_PORT="${PORT:-3000}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://localhost:3000}"
RESOLVED_SPICE_DIR="$ROOT_DIR/data/spice-kernels"
RESOLVED_DEM_ROOT="$ROOT_DIR/data/lunar-dem"
MEDIA_ROOT="${MEDIA_ROOT:-$BACKEND_DIR/storage/media}"
IMPORT_STAGING_ROOT="${IMPORT_STAGING_ROOT:-$BACKEND_DIR/storage/imports}"
CODEX_TRANSPORT_MODE="${CODEX_TRANSPORT_MODE:-mock}"
CODEX_REQUIRE_VERIFIED_BENCH="${CODEX_REQUIRE_VERIFIED_BENCH:-True}"
ALEMBIC_CURRENT=""
ALEMBIC_HEAD=""
ALEMBIC_PENDING=""

# Service status indicators for final summary banner
STATUS_DATABASE="NOT CHECKED"
STATUS_BACKEND="NOT STARTED"
STATUS_AI="FALLBACK MODE"
STATUS_SIMULATION="NOT STARTED"
STATUS_FRONTEND="NOT STARTED"
STATUS_SSR="NOT STARTED"
AI_DETAIL=""

# CLI flags
ACTION="start"
ALLOW_MIGRATE="0"
PROD_MODE="0"
NO_OPEN="${CLPS_NO_OPEN:-0}"
CLEANUP_RAN="0"

# ---------------------------------------------------------------------------
# Logging & error helpers
# ---------------------------------------------------------------------------
log_step() {
  printf "[CLPS] %s\n" "$1"
}

log_warn() {
  printf "[WARN] %s\n" "$1" >&2
}

log_err() {
  printf "[ERROR] %s\n" "$1" >&2
}

show_log_excerpt() {
  local service_name="$1"
  local log_path="$2"
  log_err "Service '$service_name' failed. Log file: $log_path"
  if [ -f "$log_path" ]; then
    log_err "--- Last 20 lines of $service_name log ---"
    tail -n 20 "$log_path" >&2 || true
    log_err "------------------------------------------"
  fi
}

usage() {
  cat <<'EOF'
CLPS Luna Browser — Single-Command Local Launcher

Usage:
  ./run_clps.sh [options]

Options:
  (default)     Validate environment, start required services in order, verify health,
                print the website URL, and keep launched services running until CTRL+C.
  --status      Inspect current service, database, Ollama model, worker, and SSR state.
  --stop        Stop only processes started by this launcher (never kills PostgreSQL or
                pre-existing Ollama/unrelated processes).
  --migrate     Opt-in to running `uv run alembic upgrade head` if DB revision is behind.
  --prod        Run Express 5 SSR in production bundle mode (`NODE_ENV=production`)
                instead of development Vite SSR middleware (`npm run dev`).
  --no-open     Do not automatically open the browser after startup.
  -h, --help    Show this help message.
EOF
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --status)
        ACTION="status"
        ;;
      --stop)
        ACTION="stop"
        ;;
      --migrate)
        ALLOW_MIGRATE="1"
        ;;
      --prod)
        PROD_MODE="1"
        ;;
      --no-open)
        NO_OPEN="1"
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        log_err "Unknown option: $1"
        usage >&2
        exit 2
        ;;
    esac
    shift
  done
}

# ---------------------------------------------------------------------------
# Safe runtime directory, lock, and PID-tree management (macOS compatible)
# ---------------------------------------------------------------------------
ensure_runtime_dirs() {
  mkdir -p "$LOG_DIR"
}

acquire_lock() {
  ensure_runtime_dirs
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    local existing_lock_pid=""
    if [ -f "$LOCK_DIR/pid" ]; then
      existing_lock_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    fi
    if [ -n "$existing_lock_pid" ] && kill -0 "$existing_lock_pid" 2>/dev/null; then
      log_err "Another run_clps.sh startup/monitor is already active (PID $existing_lock_pid)."
      log_err "Run '$ROOT_DIR/run_clps.sh --status' or '$ROOT_DIR/run_clps.sh --stop' first."
      exit 1
    fi
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR"
  fi
  printf "%s\n" "$$" > "$LOCK_DIR/pid"
}

release_lock() {
  if [ -f "$LOCK_DIR/pid" ]; then
    local lock_pid=""
    lock_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    if [ "$lock_pid" = "$$" ]; then
      rm -rf "$LOCK_DIR"
    fi
  fi
}

record_pid() {
  local svc="$1"
  local pid="$2"
  local match_hint="$3"
  local tmp_file="$PID_FILE.tmp.$$"
  touch "$PID_FILE"
  grep -v "^${svc}|" "$PID_FILE" > "$tmp_file" 2>/dev/null || true
  printf "%s|%s|%s\n" "$svc" "$pid" "$match_hint" >> "$tmp_file"
  mv "$tmp_file" "$PID_FILE"
}

get_tracked_pid_line() {
  local svc="$1"
  if [ ! -f "$PID_FILE" ]; then
    return 1
  fi
  grep "^${svc}|" "$PID_FILE" | head -n 1 || return 1
}

pid_matches_hint() {
  local pid="$1"
  local hint="$2"
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    return 1
  fi
  local cmdline=""
  cmdline="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  if [ -z "$cmdline" ]; then
    return 1
  fi
  case "$cmdline" in
    *"$hint"*) return 0 ;;
    *) return 1 ;;
  esac
}

list_descendant_pids() {
  local parent="$1"
  local child=""
  local children=""
  children="$(pgrep -P "$parent" 2>/dev/null || true)"
  for child in $children; do
    list_descendant_pids "$child"
    printf "%s\n" "$child"
  done
}

terminate_pid_tree() {
  local root_pid="$1"
  local label="$2"
  if [ -z "$root_pid" ] || ! kill -0 "$root_pid" 2>/dev/null; then
    return 0
  fi

  local descendants=""
  descendants="$(list_descendant_pids "$root_pid")"

  # Graceful SIGTERM bottom-up: descendants first, then root PID
  local dpid=""
  for dpid in $descendants; do
    kill -TERM "$dpid" 2>/dev/null || true
  done
  kill -TERM "$root_pid" 2>/dev/null || true

  local waited=0
  while [ "$waited" -lt 25 ]; do
    if ! kill -0 "$root_pid" 2>/dev/null; then
      local still_alive=0
      for dpid in $descendants; do
        if kill -0 "$dpid" 2>/dev/null; then
          still_alive=1
          break
        fi
      done
      if [ "$still_alive" -eq 0 ]; then
        return 0
      fi
    fi
    sleep 0.2
    waited=$((waited + 1))
  done

  # Force SIGKILL only on verified remaining children + root if SIGTERM timed out
  log_warn "Force stopping unresponsive $label (PID $root_pid)..."
  for dpid in $descendants; do
    kill -KILL "$dpid" 2>/dev/null || true
  done
  kill -KILL "$root_pid" 2>/dev/null || true
}

stop_tracked_services() {
  if [ ! -f "$PID_FILE" ]; then
    return 0
  fi

  # Shutdown reverse startup order: frontend_ssr -> worker -> backend -> ollama (only if started by us)
  local svc=""
  for svc in frontend_ssr worker backend ollama; do
    local line=""
    line="$(get_tracked_pid_line "$svc" || true)"
    if [ -z "$line" ]; then
      continue
    fi
    local pid=""
    local hint=""
    pid="$(printf "%s" "$line" | cut -d'|' -f2)"
    hint="$(printf "%s" "$line" | cut -d'|' -f3-)"
    if pid_matches_hint "$pid" "$hint"; then
      log_step "Stopping $svc (PID $pid)..."
      terminate_pid_tree "$pid" "$svc"
    fi
  done

  rm -f "$PID_FILE"
}

cleanup_on_exit() {
  local exit_code="$?"
  if [ "$CLEANUP_RAN" -eq 1 ]; then
    return
  fi
  CLEANUP_RAN=1
  if [ "$ACTION" = "start" ]; then
    stop_tracked_services
    release_lock
  fi
  return "$exit_code"
}

# ---------------------------------------------------------------------------
# Port & HTTP inspection helpers (macOS lsof + IPv4 curl)
# ---------------------------------------------------------------------------
get_listening_pids_on_port() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | sort -u || true
}

get_process_command() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null || true
}

get_process_cwd() {
  local pid="$1"
  lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true
}

is_local_host() {
  local host="$1"
  local lower=""
  lower="$(printf "%s" "$host" | tr '[:upper:]' '[:lower:]')"
  case "$lower" in
    localhost|127.0.0.1|::1|"[::1]") return 0 ;;
    *) return 1 ;;
  esac
}

http_code() {
  local url="$1"
  local max_time="${2:-3}"
  curl -sS -o /dev/null -w "%{http_code}" --max-time "$max_time" "$url" 2>/dev/null || printf "000"
}

# ---------------------------------------------------------------------------
# Pre-flight validation & safe non-secret config inspection
# ---------------------------------------------------------------------------
validate_base_tools() {
  local missing=""
  local cmd=""
  for cmd in bash uv node npm curl lsof python3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      missing="$missing $cmd"
    fi
  done
  if [ -n "$missing" ]; then
    log_err "Missing required system commands:$missing"
    exit 1
  fi
  if [ ! -d "$BACKEND_DIR" ] || [ ! -d "$FRONTEND_DIR" ]; then
    log_err "Invalid repository layout under $ROOT_DIR (expected backend/ and frontend/)."
    exit 1
  fi
  if [ ! -f "$ENV_FILE" ]; then
    log_err "Missing backend configuration file: $ENV_FILE"
    log_err "Copy '$BACKEND_DIR/.env.example' to '$ENV_FILE' and configure DATABASE_URL and secrets manually."
    exit 1
  fi
}

ensure_project_dependencies() {
  # Backend uv environment
  if [ ! -x "$BACKEND_DIR/.venv/bin/python" ]; then
    if [ -f "$BACKEND_DIR/uv.lock" ]; then
      log_step "Backend virtual environment missing; running 'uv sync --frozen' in backend/..."
      (cd "$BACKEND_DIR" && uv sync --frozen)
    else
      log_err "Missing $BACKEND_DIR/.venv and $BACKEND_DIR/uv.lock."
      exit 1
    fi
  fi

  # Verify critical runtime imports exist inside existing venv without altering installed packages
  if ! "$BACKEND_DIR/.venv/bin/python" -c "import fastapi, uvicorn, sqlalchemy, psycopg, alembic, spiceypy, rasterio" 2>/dev/null; then
    log_err "Backend .venv is missing required Python dependencies."
    log_err "Run: cd \"$BACKEND_DIR\" && uv sync --all-extras"
    exit 1
  fi

  # Frontend node_modules
  if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    if [ -f "$FRONTEND_DIR/package-lock.json" ]; then
      log_step "frontend/node_modules missing; installing locked dependencies with 'npm ci'..."
      (cd "$FRONTEND_DIR" && npm ci)
    else
      log_err "Missing $FRONTEND_DIR/node_modules and $FRONTEND_DIR/package-lock.json."
      exit 1
    fi
  fi

  if [ "$PROD_MODE" -eq 1 ]; then
    if [ ! -f "$FRONTEND_DIR/dist/client/index.html" ] || [ ! -f "$FRONTEND_DIR/dist/server/entry-server.js" ]; then
      log_err "Production mode (--prod) requires built artifacts in $FRONTEND_DIR/dist/."
      log_err "Run: cd \"$FRONTEND_DIR\" && npm run build"
      exit 1
    fi
  fi
}

load_runtime_metadata() {
  local write_meta="${1:-1}"
  # Inspect configuration via Pydantic Settings without exposing secrets to stdout or logs
  local eval_output=""
  eval_output="$(
    cd "$BACKEND_DIR" && .venv/bin/python - <<'PY'
import shlex
from urllib.parse import urlsplit
from app.core.config import settings

db_u = urlsplit(settings.DATABASE_URL)
ol_u = urlsplit(settings.OLLAMA_BASE_URL)
pub_u = urlsplit(settings.PUBLIC_BASE_URL)

db_host = db_u.hostname or "localhost"
db_port = str(db_u.port or 5432)
db_name = (db_u.path or "/clps_luna").lstrip("/") or "clps_luna"

ol_host = ol_u.hostname or "127.0.0.1"
ol_port = str(ol_u.port or 11434)

pub_port = str(pub_u.port or (443 if pub_u.scheme == "https" else 80))

pairs = {
    "DB_HOST": db_host,
    "DB_PORT": db_port,
    "DB_NAME": db_name,
    "OLLAMA_BASE_URL": settings.OLLAMA_BASE_URL.rstrip("/"),
    "OLLAMA_HOST": ol_host,
    "OLLAMA_PORT": ol_port,
    "OLLAMA_MODEL": settings.OLLAMA_MODEL,
    "PUBLIC_BASE_URL": settings.PUBLIC_BASE_URL.rstrip("/"),
    "CONFIGURED_SSR_PORT": pub_port,
    "RESOLVED_SPICE_DIR": settings.resolved_spice_kernel_dir,
    "RESOLVED_DEM_ROOT": settings.resolved_dem_root,
    "MEDIA_ROOT": settings.MEDIA_ROOT,
    "IMPORT_STAGING_ROOT": settings.IMPORT_STAGING_ROOT,
    "CODEX_TRANSPORT_MODE": settings.CODEX_TRANSPORT_MODE,
    "CODEX_REQUIRE_VERIFIED_BENCH": str(settings.CODEX_REQUIRE_VERIFIED_BENCH),
}
for k, v in pairs.items():
    print(f"{k}={shlex.quote(v)}")
PY
  )"
  eval "$eval_output"

  # Preserve caller environment overrides while defaulting cleanly to config/SSR contract
  BACKEND_PORT="${BACKEND_PORT:-8000}"
  if [ -n "${PORT:-}" ]; then
    SSR_PORT="$PORT"
  elif [ "$CONFIGURED_SSR_PORT" = "80" ] || [ "$CONFIGURED_SSR_PORT" = "443" ]; then
    SSR_PORT="3000"
  else
    SSR_PORT="$CONFIGURED_SSR_PORT"
  fi

  # Safety check: never boot main app against test or restore databases
  if [ "$DB_NAME" = "clps_luna_test" ] || [ "$DB_NAME" = "clps_luna_restore_test" ]; then
    log_err "Refusing to launch against non-production/test database '$DB_NAME'."
    log_err "Fix DATABASE_URL in $ENV_FILE to point to the primary application database (e.g., 'clps_luna')."
    exit 1
  fi

  if [ "$write_meta" -eq 1 ]; then
    ensure_runtime_dirs
    cat > "$META_FILE" <<EOF
ACTIVE_BACKEND_PORT=${BACKEND_PORT}
ACTIVE_SSR_PORT=${SSR_PORT}
EOF
  fi
}

validate_scientific_assets_and_storage() {
  # Runtime storage directories (resolve relative to backend/ if needed)
  local media_path="$MEDIA_ROOT"
  local import_path="$IMPORT_STAGING_ROOT"
  case "$media_path" in
    /*) ;;
    *) media_path="$BACKEND_DIR/${media_path#./}" ;;
  esac
  case "$import_path" in
    /*) ;;
    *) import_path="$BACKEND_DIR/${import_path#./}" ;;
  esac
  mkdir -p "$media_path" "$import_path"

  if [ ! -d "$RESOLVED_SPICE_DIR" ]; then
    log_err "Required SPICE kernel directory missing: $RESOLVED_SPICE_DIR"
    exit 1
  fi

  # Verify every kernel declared in manifest.json exists locally
  local missing_kernels=""
  missing_kernels="$(
    "$BACKEND_DIR/.venv/bin/python" - "$RESOLVED_SPICE_DIR" <<'PY'
import json, sys
from pathlib import Path

d = Path(sys.argv[1])
mf = d / "manifest.json"
if not mf.is_file():
    print("manifest.json")
    sys.exit(0)
data = json.loads(mf.read_text(encoding="utf-8"))
missing = [k["filename"] for k in data.get("kernels", []) if not (d / k["filename"]).is_file()]
print(" ".join(missing))
PY
  )"
  if [ -n "$missing_kernels" ]; then
    log_err "Missing required SPICE kernel files in $RESOLVED_SPICE_DIR: $missing_kernels"
    exit 1
  fi

  if [ ! -d "$RESOLVED_DEM_ROOT" ]; then
    log_err "Required LOLA DEM directory missing: $RESOLVED_DEM_ROOT"
    exit 1
  fi
  local missing_dems=""
  missing_dems="$(
    "$BACKEND_DIR/.venv/bin/python" - "$RESOLVED_DEM_ROOT" <<'PY'
import json, sys
from pathlib import Path

d = Path(sys.argv[1])
mf = d / "manifest.json"
if not mf.is_file():
    print("manifest.json")
    sys.exit(0)
data = json.loads(mf.read_text(encoding="utf-8"))
missing = [a["filename"] for a in data.get("assets", []) if not (d / a["filename"]).is_file()]
print(" ".join(missing))
PY
  )"
  if [ -n "$missing_dems" ]; then
    log_err "Missing LOLA DEM assets in $RESOLVED_DEM_ROOT: $missing_dems"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Service 1 — PostgreSQL + Alembic revision gate
# ---------------------------------------------------------------------------
detect_homebrew_postgres_formula() {
  if ! command -v brew >/dev/null 2>&1; then
    return 1
  fi
  local svc_formula=""
  svc_formula="$(brew services list 2>/dev/null | awk '/^postgresql(@[0-9]+)?[[:space:]]/{print $1; exit}' || true)"
  if [ -n "$svc_formula" ]; then
    printf "%s\n" "$svc_formula"
    return 0
  fi
  local pkg_formula=""
  pkg_formula="$(brew list --formula 2>/dev/null | grep -E '^postgresql(@[0-9]+)?$' | head -n 1 || true)"
  if [ -n "$pkg_formula" ]; then
    printf "%s\n" "$pkg_formula"
    return 0
  fi
  return 1
}

pg_accepting_connections() {
  if command -v pg_isready >/dev/null 2>&1; then
    pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1
    return $?
  fi
  (
    cd "$BACKEND_DIR" && .venv/bin/python - <<'PY' >/dev/null 2>&1
import socket, sys
from urllib.parse import urlsplit
from app.core.config import settings
u = urlsplit(settings.DATABASE_URL)
s = socket.create_connection((u.hostname or "localhost", int(u.port or 5432)), timeout=2)
s.close()
PY
  )
}

verify_database_and_migrations() {
  local db_check_out=""
  if ! db_check_out="$(
    cd "$BACKEND_DIR" && .venv/bin/python - <<'PY' 2>&1
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from app.core.config import settings
from app.db.session import engine

with engine.connect() as conn:
    actual_db = conn.execute(text("SELECT current_database()")).scalar_one()
    ctx = MigrationContext.configure(conn)
    current_rev = ctx.get_current_revision() or "<none>"

cfg = Config("alembic.ini")
script = ScriptDirectory.from_config(cfg)
head_rev = script.get_current_head() or "<none>"
pending = []
if current_rev != head_rev:
    base = None if current_rev == "<none>" else current_rev
    pending = [rev.revision for rev in script.walk_revisions(head_rev, base)]

print(f"ACTUAL_DB={actual_db}")
print(f"CURRENT_REV={current_rev}")
print(f"HEAD_REV={head_rev}")
print(f"PENDING_REVS={','.join(pending)}")
PY
  )"; then
    log_err "Could not connect to database '$DB_NAME' at ${DB_HOST}:${DB_PORT}."
    log_err "Check DATABASE_URL credentials and database existence in $ENV_FILE."
    log_err "Detail: $(printf "%s" "$db_check_out" | tail -n 5)"
    exit 1
  fi

  local ACTUAL_DB="" CURRENT_REV="" HEAD_REV="" PENDING_REVS=""
  eval "$(printf "%s\n" "$db_check_out" | grep -E '^(ACTUAL_DB|CURRENT_REV|HEAD_REV|PENDING_REVS)=')"
  ALEMBIC_CURRENT="$CURRENT_REV"
  ALEMBIC_HEAD="$HEAD_REV"
  ALEMBIC_PENDING="$PENDING_REVS"

  if [ "$ACTUAL_DB" != "$DB_NAME" ]; then
    log_err "Connected to database '$ACTUAL_DB', expected '$DB_NAME'. Aborting for safety."
    exit 1
  fi

  if [ "$ALEMBIC_CURRENT" != "$ALEMBIC_HEAD" ]; then
    log_warn "Database '$DB_NAME' Alembic revision ($ALEMBIC_CURRENT) is behind head ($ALEMBIC_HEAD)."
    log_warn "Pending revision(s): ${ALEMBIC_PENDING:-unknown}"
    if [ "$ALLOW_MIGRATE" -eq 1 ]; then
      log_step "Applying additive migrations (--migrate specified): uv run alembic upgrade head..."
      (cd "$BACKEND_DIR" && uv run alembic upgrade head)
      ALEMBIC_CURRENT="$ALEMBIC_HEAD"
    else
      log_err "Automatic migrations are disabled during normal launch to protect existing data."
      log_err "Inspect pending migrations under $BACKEND_DIR/alembic/versions and run:"
      log_err "  cd \"$BACKEND_DIR\" && uv run alembic upgrade head"
      log_err "Or re-run explicitly with: $ROOT_DIR/run_clps.sh --migrate"
      exit 1
    fi
  fi

  STATUS_DATABASE="READY ($DB_NAME @ $ALEMBIC_CURRENT)"
}

ensure_postgres_ready() {
  log_step "Checking PostgreSQL (${DB_HOST}:${DB_PORT}, db=${DB_NAME})..."
  if pg_accepting_connections; then
    log_step "PostgreSQL already running (reusing existing server)."
  else
    if ! is_local_host "$DB_HOST"; then
      log_err "Remote PostgreSQL host '$DB_HOST:$DB_PORT' is unreachable."
      exit 1
    fi
    local formula=""
    formula="$(detect_homebrew_postgres_formula || true)"
    if [ -n "$formula" ]; then
      log_step "PostgreSQL is stopped; starting installed Homebrew service '$formula'..."
      if ! brew services start "$formula" >/dev/null; then
        log_err "Failed to start Homebrew service '$formula'. Run manually: brew services start $formula"
        exit 1
      fi
      local tries=0
      while [ "$tries" -lt 40 ]; do
        if pg_accepting_connections; then
          break
        fi
        sleep 0.5
        tries=$((tries + 1))
      done
      if ! pg_accepting_connections; then
        log_err "Timed out waiting for PostgreSQL ($formula) on ${DB_HOST}:${DB_PORT}."
        log_err "Try inspecting: brew services info $formula"
        exit 1
      fi
    else
      log_err "PostgreSQL is not running on ${DB_HOST}:${DB_PORT} and no Homebrew postgresql formula was detected."
      log_err "Start your PostgreSQL server manually and re-run ./run_clps.sh."
      exit 1
    fi
  fi

  verify_database_and_migrations
}

# ---------------------------------------------------------------------------
# Service 2 — Ollama service & model inference verification
# ---------------------------------------------------------------------------
check_ollama_model_installed() {
  "$BACKEND_DIR/.venv/bin/python" -c '
import json, sys
target = sys.argv[1].strip()
data = json.load(sys.stdin)
names = [str(m.get("name", "")).strip() for m in data.get("models", [])]
print("1" if target in names else "0")
' "$OLLAMA_MODEL"
}

probe_ollama_model_inference() {
  "$BACKEND_DIR/.venv/bin/python" - "$OLLAMA_BASE_URL" "$OLLAMA_MODEL" <<'PY'
import json, sys, urllib.request

base_url = sys.argv[1].rstrip("/")
model = sys.argv[2]
payload = json.dumps({
    "model": model,
    "messages": [
        {"role": "system", "content": "Respond only with JSON: {\"ok\": true}"},
        {"role": "user", "content": "healthcheck"},
    ],
    "stream": False,
    "format": "json",
    "think": False,
    "keep_alive": "15m",
    "options": {"temperature": 0.0, "num_predict": 16},
}).encode("utf-8")

req = urllib.request.Request(
    f"{base_url}/api/chat",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=25) as resp:
        if resp.status != 200:
            sys.exit(1)
        body = json.loads(resp.read().decode("utf-8"))
        content = body.get("message", {}).get("content", "")
        json.loads(content)
        sys.exit(0)
except Exception:
    sys.exit(1)
PY
}

ensure_ollama_ready() {
  log_step "Checking Ollama service ($OLLAMA_BASE_URL, model=$OLLAMA_MODEL)..."

  local tags_code=""
  tags_code="$(http_code "$OLLAMA_BASE_URL/api/tags" 2)"

  if [ "$tags_code" = "200" ]; then
    log_step "Ollama service already running (reusing existing daemon)."
  else
    if ! command -v ollama >/dev/null 2>&1; then
      STATUS_AI="FALLBACK MODE"
      AI_DETAIL="Ollama CLI not installed (deterministic AI fallback active)"
      log_warn "$AI_DETAIL"
      return 0
    fi
    if ! is_local_host "$OLLAMA_HOST"; then
      STATUS_AI="FALLBACK MODE"
      AI_DETAIL="Remote Ollama endpoint $OLLAMA_BASE_URL unreachable (deterministic fallback active)"
      log_warn "$AI_DETAIL"
      return 0
    fi

    local port_pids=""
    port_pids="$(get_listening_pids_on_port "$OLLAMA_PORT")"
    if [ -n "$port_pids" ]; then
      STATUS_AI="FALLBACK MODE"
      AI_DETAIL="Port $OLLAMA_PORT occupied by non-Ollama process (PIDs: $port_pids); deterministic fallback active"
      log_warn "$AI_DETAIL"
      return 0
    fi

    if pgrep -x ollama >/dev/null 2>&1; then
      log_step "Existing Ollama process detected; waiting for $OLLAMA_BASE_URL/api/tags..."
    else
      log_step "Starting Ollama server (ollama serve)..."
      nohup ollama serve < /dev/null > "$LOG_DIR/ollama.log" 2>&1 &
      local ol_pid=$!
      record_pid "ollama" "$ol_pid" "ollama serve"
    fi

    local tries=0
    while [ "$tries" -lt 30 ]; do
      tags_code="$(http_code "$OLLAMA_BASE_URL/api/tags" 2)"
      if [ "$tags_code" = "200" ]; then
        break
      fi
      sleep 0.5
      tries=$((tries + 1))
    done

    if [ "$tags_code" != "200" ]; then
      STATUS_AI="FALLBACK MODE"
      AI_DETAIL="Ollama daemon did not respond on $OLLAMA_BASE_URL (deterministic fallback active; log: $LOG_DIR/ollama.log)"
      log_warn "$AI_DETAIL"
      return 0
    fi
  fi

  local tags_json=""
  tags_json="$(curl -sS --max-time 3 "$OLLAMA_BASE_URL/api/tags" 2>/dev/null || printf '{}')"
  local model_installed="0"
  model_installed="$(printf "%s" "$tags_json" | check_ollama_model_installed 2>/dev/null || printf "0")"

  if [ "$model_installed" != "1" ]; then
    STATUS_AI="FALLBACK MODE"
    AI_DETAIL="Model '$OLLAMA_MODEL' not installed (install with: ollama pull $OLLAMA_MODEL)"
    log_warn "Ollama service is running, but configured model '$OLLAMA_MODEL' is missing."
    log_warn "Install manually when ready: ollama pull $OLLAMA_MODEL"
    return 0
  fi

  log_step "Verifying Ollama model '$OLLAMA_MODEL' inference response..."
  if probe_ollama_model_inference; then
    STATUS_AI="READY"
    AI_DETAIL="model '$OLLAMA_MODEL' responding"
  else
    STATUS_AI="FALLBACK MODE"
    AI_DETAIL="Model '$OLLAMA_MODEL' installed but failed inference probe (deterministic fallback active)"
    log_warn "$AI_DETAIL"
  fi
}

# ---------------------------------------------------------------------------
# Service 3 — FastAPI Backend (uvicorn app.main:app)
# ---------------------------------------------------------------------------
backend_http_ready() {
  local health_code=""
  local ready_code=""
  health_code="$(http_code "http://127.0.0.1:${BACKEND_PORT}/api/v1/health" 2)"
  ready_code="$(http_code "http://127.0.0.1:${BACKEND_PORT}/api/v1/ready" 2)"
  [ "$health_code" = "200" ] && [ "$ready_code" = "200" ]
}

is_compatible_backend_pid() {
  local pid="$1"
  local cmd=""
  local cwd=""
  cmd="$(get_process_command "$pid")"
  cwd="$(get_process_cwd "$pid")"
  case "$cmd" in
    *uvicorn*"app.main:app"*)
      if [ "$cwd" = "$BACKEND_DIR" ] || backend_http_ready; then
        return 0
      fi
      ;;
  esac
  return 1
}

ensure_backend_ready() {
  log_step "Checking FastAPI backend (127.0.0.1:${BACKEND_PORT})..."
  local existing_pids=""
  existing_pids="$(get_listening_pids_on_port "$BACKEND_PORT")"
  if [ -n "$existing_pids" ]; then
    local compatible=0
    local epid=""
    for epid in $existing_pids; do
      if is_compatible_backend_pid "$epid"; then
        compatible=1
        break
      fi
    done
    if [ "$compatible" -eq 1 ] && backend_http_ready; then
      log_step "Compatible CLPS FastAPI backend already running on port $BACKEND_PORT (reusing)."
      STATUS_BACKEND="READY (reused existing on :$BACKEND_PORT)"
      return 0
    fi
    log_err "Port $BACKEND_PORT is already occupied by an unrelated or non-ready process:"
    for epid in $existing_pids; do
      log_err "  PID $epid: $(get_process_command "$epid")"
    done
    log_err "Stop the conflicting process manually or set BACKEND_PORT=<free_port>, then retry."
    exit 1
  fi

  log_step "Starting FastAPI backend (uvicorn app.main:app on 127.0.0.1:${BACKEND_PORT})..."
  (
    cd "$BACKEND_DIR"
    nohup "$BACKEND_DIR/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" < /dev/null > "$LOG_DIR/backend.log" 2>&1 &
    printf "%s\n" "$!" > "$RUNTIME_DIR/.last_pid"
  )
  local be_pid=""
  be_pid="$(cat "$RUNTIME_DIR/.last_pid")"
  rm -f "$RUNTIME_DIR/.last_pid"
  record_pid "backend" "$be_pid" "app.main:app"

  local tries=0
  while [ "$tries" -lt 60 ]; do
    if ! kill -0 "$be_pid" 2>/dev/null; then
      show_log_excerpt "backend" "$LOG_DIR/backend.log"
      log_err "FastAPI backend exited prematurely during startup."
      exit 1
    fi
    if backend_http_ready; then
      STATUS_BACKEND="READY"
      return 0
    fi
    sleep 0.5
    tries=$((tries + 1))
  done

  show_log_excerpt "backend" "$LOG_DIR/backend.log"
  log_err "Timed out waiting for FastAPI readiness (/api/v1/ready) on port $BACKEND_PORT."
  exit 1
}

# ---------------------------------------------------------------------------
# Service 4 — Simulation Background Worker
# ---------------------------------------------------------------------------
find_running_worker_pids() {
  ps -axo pid=,command= | awk '/[a]pp\.worker\.simulation_worker/{print $1}' || true
}

ensure_simulation_worker_ready() {
  log_step "Checking simulation background worker..."
  local running_wpids=""
  running_wpids="$(find_running_worker_pids)"
  local wpid=""
  for wpid in $running_wpids; do
    local w_cwd=""
    w_cwd="$(get_process_cwd "$wpid")"
    if [ "$w_cwd" = "$BACKEND_DIR" ]; then
      log_step "Simulation worker already running (PID $wpid; avoiding duplicate instance)."
      STATUS_SIMULATION="READY (reused existing PID $wpid)"
      return 0
    else
      log_err "Another simulation_worker process is running in a different directory ($w_cwd, PID $wpid)."
      log_err "Stop it manually before launching to prevent cross-environment job claiming."
      exit 1
    fi
  done

  log_step "Starting scientific simulation worker (python -m app.worker.simulation_worker)..."
  (
    cd "$BACKEND_DIR"
    nohup "$BACKEND_DIR/.venv/bin/python" -m app.worker.simulation_worker < /dev/null > "$LOG_DIR/worker.log" 2>&1 &
    printf "%s\n" "$!" > "$RUNTIME_DIR/.last_pid"
  )
  local worker_pid=""
  worker_pid="$(cat "$RUNTIME_DIR/.last_pid")"
  rm -f "$RUNTIME_DIR/.last_pid"
  record_pid "worker" "$worker_pid" "app.worker.simulation_worker"

  # Confirm worker stays alive and emits startup banner cleanly
  local tries=0
  while [ "$tries" -lt 10 ]; do
    if ! kill -0 "$worker_pid" 2>/dev/null; then
      show_log_excerpt "worker" "$LOG_DIR/worker.log"
      log_err "Simulation worker exited prematurely. Verify SPICE/DEM paths and PostgreSQL connectivity."
      exit 1
    fi
    if grep -q "Starting simulation worker" "$LOG_DIR/worker.log" 2>/dev/null; then
      STATUS_SIMULATION="READY"
      return 0
    fi
    sleep 0.3
    tries=$((tries + 1))
  done

  if kill -0 "$worker_pid" 2>/dev/null; then
    STATUS_SIMULATION="READY"
    return 0
  fi

  show_log_excerpt "worker" "$LOG_DIR/worker.log"
  exit 1
}

# ---------------------------------------------------------------------------
# Service 5 — Express 5 SSR & Frontend
# ---------------------------------------------------------------------------
ssr_website_ready() {
  local html_code=""
  local proxy_code=""
  html_code="$(http_code "http://127.0.0.1:${SSR_PORT}/" 5)"
  proxy_code="$(http_code "http://127.0.0.1:${SSR_PORT}/api/v1/ready" 3)"
  [ "$html_code" = "200" ] && [ "$proxy_code" = "200" ]
}

is_compatible_ssr_pid() {
  local pid="$1"
  local cmd=""
  local cwd=""
  cmd="$(get_process_command "$pid")"
  cwd="$(get_process_cwd "$pid")"
  case "$cmd" in
    *ssr-server.mjs*|*node*)
      if [ "$cwd" = "$FRONTEND_DIR" ] && ssr_website_ready; then
        return 0
      fi
      ;;
  esac
  return 1
}

ensure_ssr_frontend_ready() {
  log_step "Checking Frontend + Express 5 SSR server (127.0.0.1:${SSR_PORT})..."
  local existing_pids=""
  existing_pids="$(get_listening_pids_on_port "$SSR_PORT")"
  if [ -n "$existing_pids" ]; then
    local compatible=0
    local epid=""
    for epid in $existing_pids; do
      if is_compatible_ssr_pid "$epid"; then
        compatible=1
        break
      fi
    done
    if [ "$compatible" -eq 1 ]; then
      log_step "Compatible CLPS Express SSR server already running on port $SSR_PORT (reusing)."
      STATUS_FRONTEND="READY (reused existing on :$SSR_PORT)"
      STATUS_SSR="READY"
      return 0
    fi
    log_err "Port $SSR_PORT is already occupied by an unrelated or non-ready process:"
    for epid in $existing_pids; do
      log_err "  PID $epid: $(get_process_command "$epid")"
    done
    log_err "Stop the conflicting process manually or set PORT=<free_port>, then retry."
    exit 1
  fi

  local npm_script="dev"
  if [ "$PROD_MODE" -eq 1 ]; then
    npm_script="preview"
    log_step "Starting Express 5 SSR server (production preview via 'npm run preview')..."
  else
    log_step "Starting Express 5 SSR + Vite middleware (via 'npm run dev')..."
  fi

  (
    cd "$FRONTEND_DIR"
    PORT="$SSR_PORT" BACKEND_ORIGIN="http://127.0.0.1:${BACKEND_PORT}" \
      nohup npm run "$npm_script" < /dev/null > "$LOG_DIR/frontend_ssr.log" 2>&1 &
    printf "%s\n" "$!" > "$RUNTIME_DIR/.last_pid"
  )
  local fe_pid=""
  fe_pid="$(cat "$RUNTIME_DIR/.last_pid")"
  rm -f "$RUNTIME_DIR/.last_pid"
  record_pid "frontend_ssr" "$fe_pid" "npm"

  local tries=0
  while [ "$tries" -lt 80 ]; do
    if ! kill -0 "$fe_pid" 2>/dev/null; then
      # If npm exited while handing off, check whether node child is still starting or crashed
      if ! get_listening_pids_on_port "$SSR_PORT" | grep -q '[0-9]'; then
        show_log_excerpt "frontend_ssr" "$LOG_DIR/frontend_ssr.log"
        log_err "Express SSR / frontend failed to stay running."
        exit 1
      fi
    fi
    if ssr_website_ready; then
      # Re-record exact Node child hint cleanly if present so --stop tracks full npm+node tree
      STATUS_FRONTEND="READY"
      STATUS_SSR="READY"
      return 0
    fi
    sleep 0.5
    tries=$((tries + 1))
  done

  show_log_excerpt "frontend_ssr" "$LOG_DIR/frontend_ssr.log"
  log_err "Timed out waiting for Express SSR website health check on http://127.0.0.1:${SSR_PORT}/."
  exit 1
}

# ---------------------------------------------------------------------------
# Summary banner, optional browser open, monitor loop, --status & --stop
# ---------------------------------------------------------------------------
print_running_banner() {
  local display_url="http://localhost:${SSR_PORT}"
  printf "\n"
  printf "==================================================\n"
  printf "             CLPS LUNA BROWSER\n"
  printf "==================================================\n\n"
  printf "STATUS: RUNNING\n\n"
  printf "OPEN YOUR BROWSER:\n\n"
  printf "%s\n\n" "$display_url"
  printf "Backend:       %s\n" "$STATUS_BACKEND"
  printf "Database:      %s\n" "$STATUS_DATABASE"
  printf "AI SERVICE:    %s (%s)\n" "$STATUS_AI" "$AI_DETAIL"
  printf "SIMULATION:    %s\n" "$STATUS_SIMULATION"
  printf "FRONTEND:      %s\n" "$STATUS_FRONTEND"
  printf "SSR SERVER:    %s\n" "$STATUS_SSR"
  printf "CODEX HARDWARE:%s (require_verified_bench=%s)\n\n" " MOCK / BLOCKED" "$CODEX_REQUIRE_VERIFIED_BENCH"
  printf "Runtime Logs:  %s\n" "$LOG_DIR"
  printf "==================================================\n\n"
  printf "Press CTRL+C to stop services started by this launcher.\n"
}

open_browser_if_supported() {
  if [ "$NO_OPEN" = "1" ]; then
    return 0
  fi
  local target_url="http://localhost:${SSR_PORT}"
  if command -v open >/dev/null 2>&1; then
    open "$target_url" >/dev/null 2>&1 || log_warn "Could not open browser automatically; visit $target_url"
  fi
}

monitor_launched_processes() {
  # Wait until CTRL+C / SIGTERM, external --stop, or critical service crash
  while true; do
    if [ ! -f "$PID_FILE" ]; then
      log_step "Launcher-managed services stopped externally. Exiting monitor cleanly."
      CLEANUP_RAN=1
      release_lock
      return 0
    fi
    local svc=""
    for svc in backend worker frontend_ssr; do
      local line=""
      line="$(get_tracked_pid_line "$svc" || true)"
      if [ -n "$line" ]; then
        local pid=""
        local hint=""
        pid="$(printf "%s" "$line" | cut -d'|' -f2)"
        hint="$(printf "%s" "$line" | cut -d'|' -f3-)"
        if ! pid_matches_hint "$pid" "$hint"; then
          show_log_excerpt "$svc" "$LOG_DIR/${svc}.log"
          log_err "Critical launcher-managed service '$svc' stopped unexpectedly."
          exit 1
        fi
      fi
    done
    sleep 2
  done
}

cmd_status() {
  local env_port_set="${PORT:-}"
  validate_base_tools
  load_runtime_metadata 0
  if [ -f "$PID_FILE" ] && [ -f "$META_FILE" ]; then
    # Read ports used by active launcher session unless explicitly overridden by caller
    local active_be="" active_ssr=""
    active_be="$(grep '^ACTIVE_BACKEND_PORT=' "$META_FILE" 2>/dev/null | head -n 1 | cut -d'=' -f2 || true)"
    active_ssr="$(grep '^ACTIVE_SSR_PORT=' "$META_FILE" 2>/dev/null | head -n 1 | cut -d'=' -f2 || true)"
    if [ -n "$active_be" ] && [ -z "$USER_SUPPLIED_BACKEND_PORT" ]; then
      BACKEND_PORT="$active_be"
    fi
    if [ -n "$active_ssr" ] && [ -z "$env_port_set" ]; then
      SSR_PORT="$active_ssr"
    fi
  fi

  printf "==================================================\n"
  printf "         CLPS LUNA BROWSER — STATUS CHECK\n"
  printf "==================================================\n"

  # PostgreSQL
  if pg_accepting_connections; then
    local pg_rev=""
    pg_rev="$(
      cd "$BACKEND_DIR" && .venv/bin/python - <<'PY' 2>/dev/null || printf "ERROR"
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from app.db.session import engine
with engine.connect() as conn:
    db = conn.execute(text("SELECT current_database()")).scalar_one()
    cur = MigrationContext.configure(conn).get_current_revision() or "<none>"
head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head() or "<none>"
print(f"{db} @ {cur} (head={head})")
PY
    )"
    printf "Database:      READY (%s)\n" "$pg_rev"
  else
    printf "Database:      DOWN (%s:%s)\n" "$DB_HOST" "$DB_PORT"
  fi

  # Ollama
  local ol_code=""
  ol_code="$(http_code "$OLLAMA_BASE_URL/api/tags" 2)"
  if [ "$ol_code" = "200" ]; then
    local tjson=""
    tjson="$(curl -sS --max-time 2 "$OLLAMA_BASE_URL/api/tags" 2>/dev/null || printf '{}')"
    local installed=""
    installed="$(printf "%s" "$tjson" | check_ollama_model_installed 2>/dev/null || printf "0")"
    if [ "$installed" = "1" ]; then
      if probe_ollama_model_inference; then
        printf "AI SERVICE:    READY (model '%s' responding)\n" "$OLLAMA_MODEL"
      else
        printf "AI SERVICE:    FALLBACK MODE (model '%s' failed probe)\n" "$OLLAMA_MODEL"
      fi
    else
      printf "AI SERVICE:    FALLBACK MODE (Ollama up; '%s' not installed)\n" "$OLLAMA_MODEL"
    fi
  else
    printf "AI SERVICE:    FALLBACK MODE (Ollama offline at %s)\n" "$OLLAMA_BASE_URL"
  fi

  # Backend
  if backend_http_ready; then
    printf "Backend:       READY (http://127.0.0.1:%s)\n" "$BACKEND_PORT"
  else
    printf "Backend:       DOWN (port %s)\n" "$BACKEND_PORT"
  fi

  # Worker
  local w_pid=""
  w_pid="$(find_running_worker_pids | head -n 1 || true)"
  if [ -n "$w_pid" ]; then
    printf "SIMULATION:    READY (worker PID %s)\n" "$w_pid"
  else
    printf "SIMULATION:    DOWN (no simulation_worker running)\n"
  fi

  # Frontend / SSR
  if ssr_website_ready; then
    printf "FRONTEND/SSR:  READY (http://localhost:%s)\n" "$SSR_PORT"
  else
    printf "FRONTEND/SSR:  DOWN (port %s)\n" "$SSR_PORT"
  fi

  # Launcher PID tracking summary
  if [ -f "$PID_FILE" ] && [ -s "$PID_FILE" ]; then
    printf "\nLauncher-Managed PIDs (%s):\n" "$PID_FILE"
    cat "$PID_FILE"
  else
    printf "\nLauncher-Managed PIDs: none active\n"
  fi
  printf "Logs Directory:        %s\n" "$LOG_DIR"
}

cmd_stop() {
  if [ ! -f "$PID_FILE" ] || [ ! -s "$PID_FILE" ]; then
    log_step "No launcher-managed services are currently tracked in $PID_FILE."
    log_step "Pre-existing PostgreSQL / Ollama or external processes were not modified."
    exit 0
  fi
  stop_tracked_services
  rm -rf "$LOCK_DIR" 2>/dev/null || true
  log_step "Stopped launcher-managed services cleanly."
  log_step "PostgreSQL and any pre-existing Ollama instance were preserved."
}

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
main() {
  parse_args "$@"

  case "$ACTION" in
    status)
      cmd_status
      exit 0
      ;;
    stop)
      cmd_stop
      exit 0
      ;;
    start)
      acquire_lock
      trap 'exit 130' INT
      trap 'exit 143' TERM
      trap cleanup_on_exit EXIT

      validate_base_tools
      ensure_project_dependencies
      load_runtime_metadata
      validate_scientific_assets_and_storage

      ensure_postgres_ready
      ensure_ollama_ready
      ensure_backend_ready
      ensure_simulation_worker_ready
      ensure_ssr_frontend_ready

      print_running_banner
      open_browser_if_supported
      monitor_launched_processes
      ;;
  esac
}

main "$@"
