#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# Server Setup Script for Nidin BOS / Empire OE AI
# Run on a fresh Ubuntu 22.04/24.04 droplet as root.
#
# Usage:
#   # Personal droplet:
#   bash setup-server.sh personal ai.nidin.ai
#
#   # Empire OE droplet:
#   bash setup-server.sh empireoe ai.empireoe.com
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

MODE="${1:-personal}"    # "personal" or "empireoe"
DOMAIN="${2:-}"

if [[ -z "$DOMAIN" ]]; then
    echo "Usage: bash setup-server.sh <personal|empireoe> <domain>"
    echo "  e.g. bash setup-server.sh personal ai.nidin.ai"
    exit 1
fi

if [[ "$MODE" == "personal" ]]; then
    APP_DIR="/opt/nidin-bos"
    SERVICE_NAME="nidin-bos"
    REPO_BRANCH="main"
elif [[ "$MODE" == "empireoe" ]]; then
    APP_DIR="/opt/empireoe-clone"
    SERVICE_NAME="empireoe-clone"
    REPO_BRANCH="main"
else
    echo "ERROR: MODE must be 'personal' or 'empireoe'"
    exit 1
fi

echo "══════════════════════════════════════"
echo "  Setting up: $MODE ($DOMAIN)"
echo "  App dir:    $APP_DIR"
echo "══════════════════════════════════════"

# 1. System packages
# NOTE: PostgreSQL is NOT installed here — we use DigitalOcean Managed PostgreSQL.
# If you need a local Postgres, add: postgresql postgresql-contrib
echo "[1/9] Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev \
    nginx certbot python3-certbot-nginx \
    redis-server \
    git curl build-essential \
    libpq-dev  # needed for asyncpg (client lib only, no server)

# 2. Create deploy user
echo "[2/9] Creating deploy user..."
if ! id -u deploy &>/dev/null; then
    useradd -m -s /bin/bash deploy
fi

# 3. Clone repo
echo "[3/9] Setting up application..."
if [[ ! -d "$APP_DIR" ]]; then
    mkdir -p "$APP_DIR"
    chown deploy:deploy "$APP_DIR"
    # Clone from GitHub (user must set up deploy key or use HTTPS)
    echo "  >> Clone your repo into $APP_DIR:"
    echo "     sudo -u deploy git clone https://github.com/YOUR_REPO.git $APP_DIR"
    echo "     (or rsync from local machine)"
fi

# 4. Python venv + dependencies
echo "[4/9] Setting up Python environment..."
sudo -u deploy bash -c "
    cd \"$APP_DIR\"
    python3.11 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip wheel
    pip install -r requirements.txt
"

# 5. Configure .env
echo "[5/9] Checking .env..."
if [[ ! -f "$APP_DIR/.env" ]]; then
    if [[ "$MODE" == "personal" ]]; then
        cp "$APP_DIR/deploy/env.personal.example" "$APP_DIR/.env"
    else
        cp "$APP_DIR/deploy/env.empireoe.example" "$APP_DIR/.env"
    fi
    echo "  >> IMPORTANT: Edit $APP_DIR/.env with your actual secrets!"
    echo "     Generate keys:"
    echo "     python3 -c \"import secrets; print(secrets.token_hex(32))\""
fi
chmod 600 "$APP_DIR/.env"
chown deploy:deploy "$APP_DIR/.env"

# 6. Database migration
echo "[6/9] Running database migrations..."
sudo -u deploy bash -c "
    cd \"$APP_DIR\"
    source venv/bin/activate
    alembic upgrade head
"

# 7. Nginx + SSL
echo "[7/9] Configuring Nginx..."
if [[ "$MODE" == "personal" ]]; then
    cp "$APP_DIR/deploy/nginx-personal.conf" "/etc/nginx/sites-available/$DOMAIN"
else
    # Adjust static path for empireoe
    sed "s|/opt/nidin-bos|$APP_DIR|g" \
        "$APP_DIR/deploy/nginx-empireoe.conf" > "/etc/nginx/sites-available/$DOMAIN"
fi
ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
rm -f /etc/nginx/sites-enabled/default

# Get SSL cert (will fail if DNS isn't pointed yet — run manually after)
echo "  Getting SSL certificate..."
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "nidinnover@gmail.com" || {
    echo "  >> SSL cert failed. Point DNS A record to this server's IP, then run:"
    echo "     certbot --nginx -d $DOMAIN"
}

nginx -t && systemctl reload nginx

# 8. Systemd services
echo "[8/9] Installing systemd services..."
# Web server service
sed "s|/opt/nidin-bos|$APP_DIR|g; s|nidin-bos|$SERVICE_NAME|g" \
    "$APP_DIR/deploy/nidin-bos.service" > "/etc/systemd/system/$SERVICE_NAME.service"

# Scheduler service
sed "s|/opt/nidin-bos|$APP_DIR|g; s|nidin-bos|$SERVICE_NAME|g" \
    "$APP_DIR/deploy/nidin-bos-scheduler.service" > "/etc/systemd/system/$SERVICE_NAME-scheduler.service"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" "$SERVICE_NAME-scheduler"
systemctl start "$SERVICE_NAME" "$SERVICE_NAME-scheduler"
systemctl enable redis-server
systemctl start redis-server

# 9. Journal log rotation (prevent disk exhaustion on small droplets)
echo "[9/9] Configuring journal log rotation..."
mkdir -p /etc/systemd/journald.conf.d
cp "$APP_DIR/deploy/journald.conf" /etc/systemd/journald.conf.d/nidin-bos.conf
systemctl restart systemd-journald

echo ""
echo "══════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Edit $APP_DIR/.env with real secrets"
echo "  2. Point DNS: $DOMAIN → $(curl -s ifconfig.me)"
echo "  3. Run: certbot --nginx -d $DOMAIN"
echo "  4. Run: alembic upgrade head"
echo "  5. Seed admin: sudo -u deploy $APP_DIR/venv/bin/python -c \\"
echo "     \"from app.core.config import settings; print('Admin:', settings.ADMIN_EMAIL)\""
echo "  6. Restart: sudo systemctl restart $SERVICE_NAME"
echo ""
echo "  Logs:  journalctl -u $SERVICE_NAME -f"
echo "  Health: curl https://$DOMAIN/health"
echo "══════════════════════════════════════"
