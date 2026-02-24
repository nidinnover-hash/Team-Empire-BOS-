#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# Zero-downtime deployment script
# Run from the server as root (or with sudo).
#
# Usage:
#   bash deploy.sh /opt/personal-clone personal-clone
#   bash deploy.sh /opt/empireoe-clone empireoe-clone
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

APP_DIR="${1:-/opt/personal-clone}"
SERVICE_NAME="${2:-personal-clone}"

echo "Deploying $SERVICE_NAME from $APP_DIR..."

cd "$APP_DIR"

# 1. Pull latest code
echo "[1/5] Pulling latest code..."
sudo -u deploy git pull --ff-only

# 2. Install/update dependencies
echo "[2/5] Updating dependencies..."
sudo -u deploy bash -c "
    source $APP_DIR/venv/bin/activate
    pip install -r requirements.txt --quiet
"

# 3. Run migrations
echo "[3/5] Running migrations..."
sudo -u deploy bash -c "
    source $APP_DIR/venv/bin/activate
    cd $APP_DIR
    alembic upgrade head
"

# 4. Restart services (graceful reload)
echo "[4/5] Restarting services..."
systemctl restart "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME-scheduler"

# 5. Health check
echo "[5/5] Health check..."
sleep 3
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health)
if [[ "$HTTP_CODE" == "200" ]]; then
    echo "Deploy successful! Health check returned 200."
else
    echo "WARNING: Health check returned $HTTP_CODE. Check logs:"
    echo "  journalctl -u $SERVICE_NAME --since '5 minutes ago'"
fi
