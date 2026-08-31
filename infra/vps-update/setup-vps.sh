#!/bin/bash
set -Eeuo pipefail

APP_DIR=/opt/endlume-update-server
DATA_DIR=/var/lib/endlume-updates
ENV_FILE=/etc/endlume-update-server.env
SERVICE=/etc/systemd/system/endlume-update-server.service
CADDYFILE=/etc/caddy/Caddyfile
PORT=8443

[[ $(id -u) -eq 0 ]] || { echo 'Run as root'; exit 1; }
[[ -f /tmp/endlume-server.py ]] || { echo '/tmp/endlume-server.py missing'; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl debian-keyring debian-archive-keyring apt-transport-https python3 ufw gnupg openssl

if ! command -v caddy >/dev/null 2>&1; then
  rm -f /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

mkdir -p "$APP_DIR" "$DATA_DIR/manifests/endlume/stable" "$DATA_DIR/releases/endlume/stable"
install -m 0755 /tmp/endlume-server.py "$APP_DIR/server.py"

PUBLIC_IP="$(curl -4fsS --max-time 10 https://api.ipify.org || true)"
[[ "$PUBLIC_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Cannot determine public IPv4'; exit 1; }
HOSTNAME="${PUBLIC_IP//./-}.sslip.io"
BASE_URL="https://${HOSTNAME}:${PORT}"

if [[ ! -s "$ENV_FILE" ]]; then
  SECRET="$(openssl rand -hex 32)"
  umask 077
  cat > "$ENV_FILE" <<EOF
ENDLUME_HMAC_SECRET=$SECRET
ENDLUME_UPDATE_ROOT=$DATA_DIR
ENDLUME_BIND=127.0.0.1
ENDLUME_PORT=8788
EOF
fi
chmod 600 "$ENV_FILE"

cat > "$SERVICE" <<EOF
[Unit]
Description=ENDLUME private update server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/python3 $APP_DIR/server.py
Restart=always
RestartSec=2
User=root
Group=root
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
EOF

cat > "$CADDYFILE" <<EOF
{
  http_port 80
  https_port $PORT
}

https://$HOSTNAME:$PORT {
  encode zstd gzip
  reverse_proxy 127.0.0.1:8788
}
EOF

systemctl daemon-reload
systemctl enable --now endlume-update-server
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q '^Status: active'; then
  ufw allow 80/tcp >/dev/null || true
  ufw allow "$PORT"/tcp >/dev/null || true
fi
systemctl enable caddy >/dev/null 2>&1 || true
systemctl restart caddy

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8788/health >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8788/health >/dev/null || { journalctl -u endlume-update-server -n 100 --no-pager; exit 1; }

for _ in $(seq 1 90); do
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "$BASE_URL/health" >/dev/null || { echo "HTTPS health failed: $BASE_URL/health"; journalctl -u caddy -n 120 --no-pager; exit 1; }

cat > /root/ENDLUME-UPDATE-SERVER.txt <<EOF
ENDLUME private updater
Public IP: $PUBLIC_IP
Hostname: $HOSTNAME
Base URL: $BASE_URL
Data: $DATA_DIR
Service: endlume-update-server
HTTPS: Caddy + sslip.io
EOF

printf '%s\n' "$BASE_URL"
