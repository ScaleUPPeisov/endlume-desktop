#!/bin/bash
set -Eeuo pipefail

# Bootstrap compatibility marker: PRIVATE VPS UPDATE SERVER
# The downloaded launcher checks this exact marker before executing the live setup.

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
VPS_HOST="188.94.191.240"
VPS_USER="root"
VPS_PORT="22"
VPS_LABEL="Paris / JustHost"
KEYDIR="$HOME/.endlume-updater"
SSH_KEY="$KEYDIR/vps_deploy_ed25519"
TAURI_KEY="$KEYDIR/endlume.key"
TAURI_PUB="$TAURI_KEY.pub"
CFG="$KEYDIR/vps.env"
AGENT_DIR="$HOME/.endlume-release-agent-vps"
AGENT="$AGENT_DIR/agent.sh"
PLIST="$HOME/Library/LaunchAgents/studio.endlume.release-agent-vps.plist"
KNOWN="$HOME/.ssh/known_hosts"
TMP="$(mktemp -d /tmp/endlume-vps-simple.XXXXXX)"
LOG="$HOME/Desktop/ENDLUME-VPS-Updater-Setup.log"
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
exec > >(tee "$LOG") 2>&1
fail(){ echo; echo "❌ $1"; echo "Лог: $LOG"; exit 1; }

echo "ENDLUME • SIMPLE PRIVATE UPDATE SERVER"
echo "Сервер: $VPS_LABEL ($VPS_HOST)"
echo "Без Cloudflare • без карт • без GitHub Actions/Releases"
echo
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"
for c in ssh scp ssh-keygen ssh-keyscan python3 curl pbcopy; do command -v "$c" >/dev/null 2>&1 || fail "$c не найден"; done
mkdir -p "$KEYDIR" "$AGENT_DIR" "$HOME/Library/LaunchAgents" "$HOME/.ssh"
chmod 700 "$KEYDIR" "$AGENT_DIR" "$HOME/.ssh" || true
touch "$KNOWN"; chmod 600 "$KNOWN"

# Permanent deployment key. No VPS password is stored anywhere.
if [[ ! -s "$SSH_KEY" ]]; then
  ssh-keygen -q -t ed25519 -N '' -C 'ENDLUME update publisher' -f "$SSH_KEY"
fi
chmod 600 "$SSH_KEY"; chmod 644 "$SSH_KEY.pub"

# Refresh only this VPS host key from the network if needed.
SCAN="$TMP/hostkeys"
ssh-keyscan -T 10 -p "$VPS_PORT" "$VPS_HOST" > "$SCAN" 2>/dev/null || true
[[ -s "$SCAN" ]] || fail "Paris VPS не отвечает на SSH"
if ! ssh-keygen -F "$VPS_HOST" -f "$KNOWN" >/dev/null 2>&1; then
  cat "$SCAN" >> "$KNOWN"
fi

SSH=(ssh -i "$SSH_KEY" -p "$VPS_PORT" -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$VPS_USER@$VPS_HOST")
SCP=(scp -i "$SSH_KEY" -P "$VPS_PORT" -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)

if ! "${SSH[@]}" 'echo ENDLUME_KEY_OK' 2>/dev/null | grep -q ENDLUME_KEY_OK; then
  PUB="$(cat "$SSH_KEY.pub")"
  BOOTSTRAP="umask 077; mkdir -p /root/.ssh /etc/ssh/sshd_config.d; touch /root/.ssh/authorized_keys; grep -qxF '$PUB' /root/.ssh/authorized_keys || printf '%s\\n' '$PUB' >> /root/.ssh/authorized_keys; chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys; printf 'PermitRootLogin prohibit-password\\nPubkeyAuthentication yes\\n' > /etc/ssh/sshd_config.d/99-endlume-key.conf; rm -f /etc/ssh/sshd_config.d/00-endlume-bootstrap.conf; /usr/sbin/sshd -t && systemctl restart ssh; echo ENDLUME_KEY_READY"
  printf '%s' "$BOOTSTRAP" | pbcopy
  cat > "$HOME/Desktop/ENDLUME-ONE-TIME-VPS-COMMAND.txt" <<EOF
$BOOTSTRAP
EOF
  echo "✅ Я подготовил доступ без пароля."
  echo "✅ ОДНА команда уже скопирована в буфер обмена."
  echo
  echo "Сейчас в уже открытой консоли JustHost, где ты вошёл как root:"
  echo "1. Нажми Cmd+V"
  echo "2. Нажми Enter"
  echo "3. Дождись ENDLUME_KEY_READY"
  echo "4. Запусти ЭТОТ ЖЕ установщик ещё раз"
  echo
  echo "После этого IP и пароль больше никогда не понадобятся."
  exit 20
fi

echo "✅ Доступ к Paris VPS по ключу работает — пароль не нужен"

echo "1/6 Устанавливаю общий private update-server…"
for f in infra/vps-update/server.py infra/vps-update/setup-vps.sh; do
  out="$TMP/$(basename "$f")"
  gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/$f?ref=$BRANCH" > "$out" || fail "не удалось скачать $f"
done
python3 -m py_compile "$TMP/server.py" || fail "server.py syntax error"
/bin/bash -n "$TMP/setup-vps.sh" || fail "setup-vps.sh syntax error"
"${SCP[@]}" "$TMP/server.py" "$VPS_USER@$VPS_HOST:/tmp/endlume-server.py"
"${SCP[@]}" "$TMP/setup-vps.sh" "$VPS_USER@$VPS_HOST:/tmp/endlume-setup-vps.sh"
REMOTE_LOG="$TMP/remote.log"
"${SSH[@]}" 'bash /tmp/endlume-setup-vps.sh' 2>&1 | tee "$REMOTE_LOG" || fail "VPS update-server install failed"
BASE_URL="$(grep -E '^https://[^ ]+$' "$REMOTE_LOG" | tail -1 || true)"
[[ -n "$BASE_URL" ]] || fail "VPS не вернул HTTPS endpoint"
curl -fsS "$BASE_URL/health" >/dev/null || fail "HTTPS health не отвечает"
echo "✅ $BASE_URL"

echo "2/6 Сохраняю локальную конфигурацию…"
umask 077
cat > "$CFG" <<EOF
ENDLUME_VPS_HOST='$VPS_HOST'
ENDLUME_VPS_USER='$VPS_USER'
ENDLUME_VPS_PORT='$VPS_PORT'
ENDLUME_UPDATE_BASE_URL='$BASE_URL'
EOF
chmod 600 "$CFG"

echo "3/6 Создаю постоянный Tauri signing key…"
if [[ ! -s "$TAURI_KEY" || ! -s "$TAURI_PUB" ]]; then
  rm -f "$TAURI_KEY" "$TAURI_PUB"
  npx --yes @tauri-apps/cli@2.10.1 signer generate -w "$TAURI_KEY" --ci || fail "Tauri signer generate failed"
fi
chmod 600 "$TAURI_KEY"; [[ -s "$TAURI_PUB" ]] || fail "Tauri public key отсутствует"
PUBLIC_KEY="$(tr -d '\r\n' < "$TAURI_PUB")"

echo "4/6 Сохраняю безопасный bootstrap…"
BOOT="$TMP/bootstrap.json"
python3 - "$BOOT" "$BASE_URL" "$PUBLIC_KEY" <<'PY'
import json,sys,datetime
json.dump({
 'provider':'self-hosted-vps',
 'baseUrl':sys.argv[2],
 'endpoint':sys.argv[2]+'/v1/update/endlume/{{target}}/{{arch}}/{{current_version}}',
 'genericEndpoint':sys.argv[2]+'/v1/update/{app}/{{target}}/{{arch}}/{{current_version}}',
 'pubkey':sys.argv[3],
 'buildTransport':'local-builder-ssh-no-actions',
 'storage':'own-vps',
 'platforms':['darwin-aarch64','windows-x86_64','windows-aarch64'],
 'updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()
},open(sys.argv[1],'w'),indent=2)
PY
SHA="$(gh api "/repos/$REPO/contents/updates/vps/bootstrap.json?ref=$BRANCH" --jq .sha 2>/dev/null || true)"
python3 - "$BOOT" "$TMP/payload.json" "$BRANCH" "$SHA" <<'PY'
import json,sys,base64,pathlib
src,out,branch,sha=sys.argv[1:]
p={'message':'Configure simple private VPS updater','branch':branch,'content':base64.b64encode(pathlib.Path(src).read_bytes()).decode()}
if sha:p['sha']=sha
json.dump(p,open(out,'w'))
PY
gh api --method PUT "/repos/$REPO/contents/updates/vps/bootstrap.json" --input "$TMP/payload.json" >/dev/null || fail "bootstrap save failed"

echo "5/6 Устанавливаю локальный Release Agent…"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/scripts/endlume-release-agent-vps-macos.sh?ref=$BRANCH" > "$AGENT" || fail "agent download failed"
chmod 755 "$AGENT"; /bin/bash -n "$AGENT" || fail "agent syntax error"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>studio.endlume.release-agent-vps</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>$AGENT</string></array>
<key>RunAtLoad</key><true/><key>StartInterval</key><integer>60</integer><key>ProcessType</key><string>Background</string>
<key>EnvironmentVariables</key><dict><key>HOME</key><string>$HOME</string><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
<key>StandardOutPath</key><string>$AGENT_DIR/launchd.out.log</string><key>StandardErrorPath</key><string>$AGENT_DIR/launchd.err.log</string>
</dict></plist>
EOF
plutil -lint "$PLIST" >/dev/null || fail "LaunchAgent plist invalid"
UID_NOW="$(id -u)"; launchctl bootout "gui/$UID_NOW" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_NOW" "$PLIST" || fail "LaunchAgent bootstrap failed"
launchctl kickstart -k "gui/$UID_NOW/studio.endlume.release-agent-vps" >/dev/null 2>&1 || true

echo "6/6 Готово"
cat > "$HOME/Desktop/APP-UPDATE-SERVER.txt" <<EOF
PRIVATE APP UPDATE SERVER
VPS: $VPS_LABEL / $VPS_HOST
Endpoint: $BASE_URL
macOS + Windows
Cloudflare: NO
GitHub Actions/Releases: NO
SSH password: NO (key only)
Signing private key: $TAURI_KEY (PRIVATE)
EOF

echo
echo "✅ PRIVATE UPDATE SERVER READY"
echo "✅ macOS + Windows"
echo "✅ Один сервер для всех приложений"
echo "✅ Без IP/паролей при будущих обновлениях"
echo "✅ Без Cloudflare/GitHub Actions/Releases"
echo "✅ build-request сейчас выключен — случайная сборка не стартует"
