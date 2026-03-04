#!/usr/bin/env bash
# Zero-downtime deployment script
# Run from the server as root (or with sudo).
#
# Uses Gunicorn graceful reload (HUP) to cycle workers without dropping
# in-flight requests.  On health-check failure the previous commit is
# restored and services restarted.
#
# Usage:
#   bash deploy.sh [--dry-run] [--require-backup] /opt/nidin-bos nidin-bos /opt/nidin-bos/.env
#   bash deploy.sh [--dry-run] [--require-backup] /opt/empireoe-clone empireoe-clone /opt/empireoe-clone/.env
set -euo pipefail

DRY_RUN=false
REQUIRE_BACKUP=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --require-backup)
            REQUIRE_BACKUP=true
            shift
            ;;
        --help|-h)
            echo "Usage: bash deploy.sh [--dry-run] [--require-backup] [APP_DIR] [SERVICE_NAME] [ENV_FILE]"
            exit 0
            ;;
        --)
            shift
            break
            ;;
        *)
            break
            ;;
    esac
done

APP_DIR="${1:-/opt/nidin-bos}"
SERVICE_NAME="${2:-nidin-bos}"
ENV_FILE="${3:-$APP_DIR/.env}"
HEALTH_RETRIES=5
HEALTH_DELAY=3
BACKUP_DIR="$APP_DIR/Data/backups"

echo "Deploying $SERVICE_NAME from $APP_DIR..."
echo "  Dry run: $DRY_RUN"
echo "  Require backup: $REQUIRE_BACKUP"

cd "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: env file not found: $ENV_FILE"
    exit 1
fi

read_env_var() {
    local var_name="$1"
    sudo -u deploy bash -c "
        set -a
        source \"$ENV_FILE\"
        set +a
        printf '%s' \"\${$var_name:-}\"
    "
}

# Detect health-check port from GUNICORN_BIND in .env (default 8000)
GUNICORN_BIND="$(read_env_var GUNICORN_BIND || true)"
if [[ "$GUNICORN_BIND" =~ :([0-9]+)$ ]]; then
    HEALTH_PORT="${BASH_REMATCH[1]}"
else
    HEALTH_PORT="8000"
fi
echo "  Health-check port: $HEALTH_PORT"

DB_URL="$(read_env_var DATABASE_URL || true)"
if [[ -z "$DB_URL" ]]; then
    echo "ERROR: DATABASE_URL not found in $ENV_FILE"
    exit 1
fi

# Record current commit so we can rollback on failure
PREV_COMMIT=$(sudo -u deploy git rev-parse HEAD)
CURRENT_BRANCH=$(sudo -u deploy git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT_BRANCH" == "HEAD" ]]; then
    echo "ERROR: repository is in detached HEAD state. Checkout a branch before deploying."
    exit 1
fi
echo "  Previous commit: $PREV_COMMIT"
echo "  Current branch: $CURRENT_BRANCH"

if $DRY_RUN; then
    echo "[dry-run] Validating deploy prerequisites..."
    [[ -f "$APP_DIR/venv/bin/activate" ]] || { echo "ERROR: missing venv at $APP_DIR/venv"; exit 1; }
    if [[ "$DB_URL" == postgresql* ]] && ! command -v pg_dump >/dev/null 2>&1; then
        if $REQUIRE_BACKUP; then
            echo "ERROR: pg_dump not found while --require-backup is set."
            exit 1
        fi
        echo "WARNING: pg_dump not found; backup would be skipped for PostgreSQL."
    fi
    echo "[dry-run] Would deploy commit: $(sudo -u deploy git rev-parse origin/$CURRENT_BRANCH)"
    echo "[dry-run] Prerequisites look good."
    exit 0
fi

# 1. Pull latest code
echo "[1/7] Pulling latest code..."
sudo -u deploy git fetch origin "$CURRENT_BRANCH"
sudo -u deploy git checkout "$CURRENT_BRANCH"
sudo -u deploy git pull --ff-only origin "$CURRENT_BRANCH"
NEW_COMMIT=$(sudo -u deploy git rev-parse HEAD)
echo "  New commit: $NEW_COMMIT"

# 2. Install/update dependencies
echo "[2/7] Updating dependencies..."
sudo -u deploy bash -c "
    source \"$APP_DIR/venv/bin/activate\"
    pip install -r requirements.txt --quiet
"

# 3. Validate production profile and startup settings before migrations/restart.
echo "[3/7] Running preflight checks..."
sudo -u deploy bash -c "
    set -a
    source \"$ENV_FILE\"
    set +a
    source \"$APP_DIR/venv/bin/activate\"
    python scripts/preflight_deploy.py
"

# 4. Backup DB before migrations
echo "[4/8] Creating pre-migration backup..."
mkdir -p "$BACKUP_DIR"
BACKUP_TS=$(date -u +%Y%m%d_%H%M%S)
DB_BACKUP_FILE=""
if [[ "$DB_URL" == sqlite* ]]; then
    SQLITE_PATH="$(echo "$DB_URL" | sed -E 's#^sqlite\+aiosqlite:///##; s#^sqlite:///##; s#\?.*$##')"
    if [[ "$SQLITE_PATH" != /* ]]; then
        SQLITE_PATH="$APP_DIR/$SQLITE_PATH"
    fi
    if [[ -f "$SQLITE_PATH" ]]; then
        DB_BACKUP_FILE="$BACKUP_DIR/sqlite_predeploy_${BACKUP_TS}.db"
        cp "$SQLITE_PATH" "$DB_BACKUP_FILE"
    elif $REQUIRE_BACKUP; then
        echo "ERROR: SQLite DB file not found at $SQLITE_PATH and --require-backup is set."
        exit 1
    fi
else
    if command -v pg_dump >/dev/null 2>&1; then
        DB_BACKUP_FILE="$BACKUP_DIR/postgres_predeploy_${BACKUP_TS}.sql"
        PG_DUMP_URL=$(echo "$DB_URL" | sed -E 's#^postgresql\+asyncpg://#postgresql://#; s#^postgresql\+psycopg://#postgresql://#; s#\?.*$##')
        pg_dump --dbname "$PG_DUMP_URL" --file "$DB_BACKUP_FILE"
    elif $REQUIRE_BACKUP; then
        echo "ERROR: pg_dump not found and --require-backup is set."
        exit 1
    else
        echo "  WARNING: pg_dump not found; skipping DB backup."
    fi
fi
if [[ -n "$DB_BACKUP_FILE" ]]; then
    echo "  Backup written: $DB_BACKUP_FILE"
fi

# 5. Run migrations
echo "[5/8] Running migrations..."
sudo -u deploy bash -c "
    source \"$APP_DIR/venv/bin/activate\"
    set -a
    source \"$ENV_FILE\"
    set +a
    cd \"$APP_DIR\"
    alembic upgrade head
"

# 6. Graceful reload (zero-downtime worker cycling via SIGHUP)
echo "[6/8] Graceful reload of web workers..."
systemctl reload "$SERVICE_NAME" || {
    echo "  reload not supported, falling back to restart..."
    systemctl restart "$SERVICE_NAME"
}
systemctl restart "$SERVICE_NAME-scheduler"

# 7. Health check with retries
echo "[7/8] Health check (up to $HEALTH_RETRIES attempts)..."
HEALTHY=false
for i in $(seq 1 "$HEALTH_RETRIES"); do
    sleep "$HEALTH_DELAY"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$HEALTH_PORT/health || echo "000")
    echo "  attempt $i: HTTP $HTTP_CODE"
    if [[ "$HTTP_CODE" == "200" ]]; then
        HEALTHY=true
        break
    fi
done

if $HEALTHY; then
    echo "Deploy successful ($NEW_COMMIT)."
    exit 0
fi

# 8. Rollback on failure
echo "[8/8] Health check FAILED — rolling back to $PREV_COMMIT on branch $CURRENT_BRANCH..."
sudo -u deploy git checkout "$CURRENT_BRANCH"
sudo -u deploy git reset --hard "$PREV_COMMIT"
sudo -u deploy bash -c "
    source \"$APP_DIR/venv/bin/activate\"
    pip install -r requirements.txt --quiet
"
systemctl restart "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME-scheduler"
sleep "$HEALTH_DELAY"
ROLLBACK_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$HEALTH_PORT/health || echo "000")
if [[ "$ROLLBACK_CODE" == "200" ]]; then
    echo "Rollback successful (back on $PREV_COMMIT). Deploy ABORTED."
    if [[ -n "$DB_BACKUP_FILE" ]]; then
        echo "NOTE: DB migrations were already applied. If schema mismatch occurs, restore from: $DB_BACKUP_FILE"
    fi
else
    echo "CRITICAL: rollback health check also failed ($ROLLBACK_CODE). Manual intervention required."
    echo "  journalctl -u $SERVICE_NAME --since '5 minutes ago'"
fi
exit 1
