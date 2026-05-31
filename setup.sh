#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# setup.sh — complete VPS setup for general-creation.xyz
# Run this ONCE on a fresh Ubuntu 24.04 VPS
# ═══════════════════════════════════════════════════════════════

set -e

DOMAIN="general-creation.xyz"
EMAIL="your@email.com"        # ← change this before running

echo "================================================"
echo " Content Automation Setup"
echo " Domain: $DOMAIN"
echo "================================================"

# ── 1. Install Docker ─────────────────────────────────────────
echo ""
echo "[1/4] Installing Docker..."
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

echo "✓ Docker installed"

# ── 2. Start stack (HTTP only first — needed for certbot) ─────
echo ""
echo "[2/4] Starting stack..."

# Start with HTTP-only config first (no SSL yet)
# Temporarily use simple redirect that allows certbot through
cp ./nginx/conf.d/00-redirect.conf ./nginx/conf.d/00-redirect.conf.bak
cat > ./nginx/conf.d/00-redirect.conf << 'NGINX'
server {
    listen 80;
    server_name
        general-creation.xyz www.general-creation.xyz
        analytics.general-creation.xyz n8n.general-creation.xyz
        arcreel.general-creation.xyz openclaw.general-creation.xyz
        api.general-creation.xyz;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 "Stack starting...";
        add_header Content-Type text/plain;
    }
}
NGINX

# Comment out SSL server blocks temporarily
for conf in ./nginx/conf.d/0[1-5]-*.conf; do
    sed -i 's/^server {/# server {/' "$conf"  2>/dev/null || true
done

docker compose build
docker compose up -d nginx certbot postgres
echo "Waiting for containers..."
sleep 10

# ── 3. Get SSL certificates ───────────────────────────────────
echo ""
echo "[3/4] Getting SSL certificates..."
echo "Make sure these DNS records exist (A records → this VPS IP):"
echo "  $DOMAIN"
echo "  www.$DOMAIN"
echo "  analytics.$DOMAIN"
echo "  n8n.$DOMAIN"
echo "  arcreel.$DOMAIN"
echo "  openclaw.$DOMAIN"
echo "  api.$DOMAIN"
echo ""
read -p "DNS records configured? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Set up DNS first, then re-run this script."
    exit 1
fi

docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN" \
    -d "www.$DOMAIN" \
    -d "analytics.$DOMAIN" \
    -d "n8n.$DOMAIN" \
    -d "arcreel.$DOMAIN" \
    -d "openclaw.$DOMAIN" \
    -d "api.$DOMAIN"

echo "✓ SSL certificates obtained"

# ── 4. Restore configs + start everything ─────────────────────
echo ""
echo "[4/4] Starting full stack with SSL..."

# Restore original redirect config
mv ./nginx/conf.d/00-redirect.conf.bak ./nginx/conf.d/00-redirect.conf

# Restore SSL server blocks
for conf in ./nginx/conf.d/0[1-5]-*.conf; do
    sed -i 's/^# server {/server {/' "$conf" 2>/dev/null || true
done

# Start all services
docker compose up -d
sleep 15

echo ""
echo "================================================"
echo " ✅ Setup complete!"
echo ""
echo " 📊 Analytics:  https://analytics.$DOMAIN"
echo " 🔧 n8n:        https://n8n.$DOMAIN"
echo " 🎬 ArcReel:    https://arcreel.$DOMAIN"
echo " 🤖 OpenClaw:   https://openclaw.$DOMAIN"
echo " 🔌 API:        https://api.$DOMAIN/health"
echo ""
echo " SSL auto-renews every 12 hours via certbot container"
echo "================================================"
