#!/usr/bin/env bash
# Zero-downtime deployment script
# Run from the server as root (or with sudo).
#
# Usage:
#   bash deploy.sh /opt/personal-clone personal-clone /opt/personal-clone/.env
#   bash deploy.sh /opt/empireoe-clone empireoe-clone /opt/empireoe-clone/.env
set -euo pipefail

APP_DIR="${1:-/opt/personal-clone}"
SERVICE_NAME="${2:-personal-clone}"
ENV_FILE="${3:-$APP_DIR/.env}"

echo "Deploying $SERVICE_NAME from $APP_DIR..."

cd "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: env file not found: $ENV_FILE"
    exit 1
fi

# 1. Pull latest code
echo "[1/6] Pulling latest code..."
sudo -u deploy git pull --ff-only

# 2. Install/update dependencies
echo "[2/6] Updating dependencies..."
sudo -u deploy bash -c "
    source $APP_DIR/venv/bin/activate
    pip install -r requirements.txt --quiet
"

# 3. Validate production profile and startup settings before migrations/restart.
echo "[3/6] Validating environment and startup settings..."
sudo -u deploy bash -c "
    set -a
    source \"$ENV_FILE\"
    set +a
    source \"$APP_DIR/venv/bin/activate\"
    if [[ \"\${DEBUG:-false}\" != \"false\" ]]; then
        echo 'ERROR: DEBUG must be false in production'
        exit 1
    fi
    if [[ \"\${ENFORCE_STARTUP_VALIDATION:-false}\" != \"true\" ]]; then
        echo 'ERROR: ENFORCE_STARTUP_VALIDATION must be true in production'
        exit 1
    fi
    if [[ \"\${COOKIE_SECURE:-false}\" != \"true\" ]]; then
        echo 'ERROR: COOKIE_SECURE must be true in production'
        exit 1
    fi
    if [[ \"\${DATABASE_URL:-}\" == sqlite* ]]; then
        echo 'ERROR: DATABASE_URL cannot use sqlite in production'
        exit 1
    fi
    python -c \"from app.core.config import settings, validate_startup_settings, format_startup_issues; issues=validate_startup_settings(settings); print('startup validation passed' if not issues else format_startup_issues(issues)); raise SystemExit(1 if issues else 0)\"
"

# 4. Run migrations
echo "[4/6] Running migrations..."
sudo -u deploy bash -c "
    source \"$APP_DIR/venv/bin/activate\"
    set -a
    source \"$ENV_FILE\"
    set +a
    cd \"$APP_DIR\"
    alembic upgrade head
"

# 5. Restart services
echo "[5/6] Restarting services..."
systemctl restart "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME-scheduler"

# 6. Health check
echo "[6/6] Health check..."
sleep 3
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health)
if [[ "$HTTP_CODE" == "200" ]]; then
    echo "Deploy successful: health check returned 200."
else
    echo "WARNING: health check returned $HTTP_CODE. Check logs:"
    echo "  journalctl -u $SERVICE_NAME --since '5 minutes ago'"
fi
