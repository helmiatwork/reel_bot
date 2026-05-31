#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# setup-nginx.sh — run this ONCE on your VPS
# Sets up Nginx + SSL for general-creation.xyz
# ═══════════════════════════════════════════════════════════════

set -e

DOMAIN="general-creation.xyz"
DASHBOARD_DIR="/var/www/content-automation"

echo "================================================"
echo " Setting up Nginx for $DOMAIN"
echo "================================================"

# ── 1. Install Nginx ───────────────────────────────────────────
echo "[1/5] Installing Nginx..."
apt-get update -q
apt-get install -y nginx certbot python3-certbot-nginx

# ── 2. Copy dashboard files ────────────────────────────────────
echo "[2/5] Deploying analytics dashboard..."
mkdir -p "$DASHBOARD_DIR"
cp ./analytics-dashboard/index.html "$DASHBOARD_DIR/"
chown -R www-data:www-data "$DASHBOARD_DIR"
chmod -R 755 "$DASHBOARD_DIR"

# ── 3. Install Nginx config ────────────────────────────────────
echo "[3/5] Installing Nginx config..."
cp ./nginx/$DOMAIN.conf /etc/nginx/sites-available/$DOMAIN
ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/$DOMAIN

# Remove default site
rm -f /etc/nginx/sites-enabled/default

# Test config
nginx -t

# ── 4. Start / reload Nginx ────────────────────────────────────
echo "[4/5] Starting Nginx..."
systemctl enable nginx
systemctl restart nginx

echo ""
echo "✓ Nginx running"
echo "  Dashboard:    http://$DOMAIN/"
echo "  Pipeline API: http://$DOMAIN/api/health"
echo "  n8n:          http://$DOMAIN/n8n/"
echo "  ArcReel:      http://$DOMAIN/arcreel/"
echo ""

# ── 5. SSL with Let's Encrypt ──────────────────────────────────
echo "[5/5] Setting up SSL (Let's Encrypt)..."
echo ""
echo "Make sure your DNS A record points $DOMAIN → this VPS IP"
echo "Then run:"
echo ""
echo "  certbot --nginx -d $DOMAIN -d www.$DOMAIN"
echo ""
echo "After certbot, uncomment the HTTPS block in:"
echo "  /etc/nginx/sites-available/$DOMAIN"
echo ""
echo "Auto-renew is already set up by certbot."
echo ""
echo "================================================"
echo " Setup complete!"
echo "================================================"
