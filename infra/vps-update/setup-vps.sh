#!/bin/bash
set -Eeuo pipefail

APP_DIR=/opt/endlume-update-server
DATA_DIR=/var/lib/endlume-updates
ENV_FILE=/etc/endlume-update-server.env
SERVICE=/etc/systemd/system/endlume-update-server.service
CADDYFILE=/etc/caddy/Caddyfile
CLEANUP=/usr/local/sbin/private-update-cleanup
CLEANUP_SERVICE=/etc/systemd/system/private-update-cleanup.service
CLEANUP_TIMER=/etc/systemd/system/private-update-cleanup.timer
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

mkdir -p "$APP_DIR" "$DATA_DIR/manifests" "$DATA_DIR/releases"
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
Description=Private application update server
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

cat > "$CLEANUP" <<'PY'
#!/usr/bin/env python3
import json,time
from pathlib import Path
ROOT=Path('/var/lib/endlume-updates').resolve()
MAN=ROOT/'manifests'
REL=ROOT/'releases'
keep=set()
for p in MAN.rglob('*.json') if MAN.exists() else []:
    try:
        d=json.loads(p.read_text('utf-8'))
        k=str(d.get('object_key','')).strip()
        if k:
            q=(ROOT/k).resolve()
            q.relative_to(ROOT)
            keep.add(q)
    except Exception:
        pass
cutoff=time.time()-24*3600
if REL.exists():
    for p in sorted(REL.rglob('*'),reverse=True):
        try:
            if p.is_file() and p.resolve() not in keep and p.stat().st_mtime < cutoff:
                p.unlink()
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        except Exception:
            pass
PY
chmod 0755 "$CLEANUP"

cat > "$CLEANUP_SERVICE" <<EOF
[Unit]
Description=Clean old private updater artifacts

[Service]
Type=oneshot
ExecStart=$CLEANUP
EOF

cat > "$CLEANUP_TIMER" <<'EOF'
[Unit]
Description=Hourly cleanup of old private updater artifacts

[Timer]
OnBootSec=10m
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now endlume-update-server
systemctl enable --now private-update-cleanup.timer
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

cat > /root/PRIVATE-APP-UPDATE-SERVER.txt <<EOF
Private updater
Public IP: $PUBLIC_IP
Hostname: $HOSTNAME
Base URL: $BASE_URL
Data: $DATA_DIR
Service: endlume-update-server
HTTPS: Caddy + sslip.io
Cleanup: hourly, keeps manifest-referenced builds; stale unreferenced files removed after 24h
EOF

printf '%s\n' "$BASE_URL"
