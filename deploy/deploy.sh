#!/usr/bin/env bash
# Zero-downtime deployment script
# Run from the server as root (or with sudo).
#
# Usage:
#   bash deploy.sh /opt/nidin-nover-ai nidin-nover-ai /opt/nidin-nover-ai/.env
#   bash deploy.sh /opt/empireoe-clone empireoe-clone /opt/empireoe-clone/.env
set -euo pipefail

APP_DIR="${1:-/opt/nidin-nover-ai}"
SERVICE_NAME="${2:-nidin-nover-ai}"
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
echo "[3/6] Running preflight checks..."
sudo -u deploy bash -c "
    set -a
    source \"$ENV_FILE\"
    set +a
    source \"$APP_DIR/venv/bin/activate\"
    python scripts/preflight_deploy.py
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
