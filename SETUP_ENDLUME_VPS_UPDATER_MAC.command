#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
KEYDIR="$HOME/.endlume-updater"
SSH_KEY="$KEYDIR/vps_deploy_ed25519"
TAURI_KEY="$KEYDIR/endlume.key"
TAURI_PUB="$TAURI_KEY.pub"
CFG="$KEYDIR/vps.env"
AGENT_DIR="$HOME/.endlume-release-agent-vps"
AGENT="$AGENT_DIR/agent.sh"
PLIST="$HOME/Library/LaunchAgents/studio.endlume.release-agent-vps.plist"
TMP="$(mktemp -d /tmp/endlume-vps-updater.XXXXXX)"
LOG="$HOME/Desktop/ENDLUME-VPS-Updater-Setup.log"
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
exec > >(tee "$LOG") 2>&1
fail(){ echo; echo "❌ $1"; echo "Лог: $LOG"; exit 1; }

echo "ENDLUME • PRIVATE VPS UPDATE SERVER"
echo "Без Cloudflare • без карт • без GitHub Actions/Releases"
echo
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"
command -v ssh >/dev/null 2>&1 || fail "ssh не найден"
command -v scp >/dev/null 2>&1 || fail "scp не найден"
mkdir -p "$KEYDIR" "$AGENT_DIR" "$HOME/Library/LaunchAgents"; chmod 700 "$KEYDIR" "$AGENT_DIR" || true

DEFAULT_HOST=""
if [[ -s "$CFG" ]]; then
  set +u; source "$CFG"; set -u
  DEFAULT_HOST="${ENDLUME_VPS_HOST:-}"
fi
printf 'IP или hostname твоего Ubuntu VPS%s: ' "${DEFAULT_HOST:+ [$DEFAULT_HOST]}"
read -r VPS_HOST
VPS_HOST="${VPS_HOST:-$DEFAULT_HOST}"
[[ -n "$VPS_HOST" ]] || fail "VPS host не указан"
printf 'SSH user [root]: '; read -r VPS_USER; VPS_USER="${VPS_USER:-root}"
printf 'SSH port [22]: '; read -r VPS_PORT; VPS_PORT="${VPS_PORT:-22}"
[[ "$VPS_PORT" =~ ^[0-9]+$ ]] || fail "SSH port некорректен"

echo
echo "1/7 Готовлю постоянный SSH-ключ ENDLUME…"
if [[ ! -s "$SSH_KEY" ]]; then
  ssh-keygen -q -t ed25519 -N '' -C 'ENDLUME update publisher' -f "$SSH_KEY"
fi
chmod 600 "$SSH_KEY"; chmod 644 "$SSH_KEY.pub"
echo "Сейчас SSH может ОДИН РАЗ попросить пароль от VPS — это нормально."
cat "$SSH_KEY.pub" | ssh -p "$VPS_PORT" -o StrictHostKeyChecking=accept-new "$VPS_USER@$VPS_HOST" 'umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; key=$(cat); grep -qxF "$key" ~/.ssh/authorized_keys || printf "%s\n" "$key" >> ~/.ssh/authorized_keys' || fail "не удалось установить SSH key на VPS"
ssh -i "$SSH_KEY" -p "$VPS_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$VPS_USER@$VPS_HOST" 'echo ENDLUME_SSH_OK' | grep -q ENDLUME_SSH_OK || fail "автоматический SSH по ключу не работает"
echo "✅ SSH key готов"

echo "2/7 Получаю VPS update-server из приватного репозитория…"
for f in infra/vps-update/server.py infra/vps-update/setup-vps.sh; do
  out="$TMP/$(basename "$f")"
  gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/$f?ref=$BRANCH" > "$out" || fail "не удалось скачать $f"
done
python3 -m py_compile "$TMP/server.py" || fail "server.py syntax error"
/bin/bash -n "$TMP/setup-vps.sh" || fail "setup-vps.sh syntax error"

echo "3/7 Устанавливаю update-server на VPS…"
SCP=(scp -i "$SSH_KEY" -P "$VPS_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
SSH=(ssh -i "$SSH_KEY" -p "$VPS_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$VPS_USER@$VPS_HOST")
"${SCP[@]}" "$TMP/server.py" "$VPS_USER@$VPS_HOST:/tmp/endlume-server.py"
"${SCP[@]}" "$TMP/setup-vps.sh" "$VPS_USER@$VPS_HOST:/tmp/endlume-setup-vps.sh"
if [[ "$VPS_USER" == root ]]; then
  REMOTE_CMD="bash /tmp/endlume-setup-vps.sh"
else
  REMOTE_CMD="sudo bash /tmp/endlume-setup-vps.sh"
fi
REMOTE_LOG="$TMP/remote.log"
"${SSH[@]}" "$REMOTE_CMD" 2>&1 | tee "$REMOTE_LOG" || fail "установка update-server на VPS завершилась ошибкой"
BASE_URL="$(grep -E '^https://[^ ]+$' "$REMOTE_LOG" | tail -1 || true)"
[[ -n "$BASE_URL" ]] || fail "VPS не вернул HTTPS endpoint"
curl -fsS "$BASE_URL/health" | grep -q 'endlume-vps-update' || fail "публичный HTTPS /health не отвечает"
echo "✅ Update Server: $BASE_URL"

echo "4/7 Сохраняю конфигурацию публикации на Mac…"
umask 077
cat > "$CFG" <<EOF
ENDLUME_VPS_HOST='$VPS_HOST'
ENDLUME_VPS_USER='$VPS_USER'
ENDLUME_VPS_PORT='$VPS_PORT'
ENDLUME_UPDATE_BASE_URL='$BASE_URL'
EOF
chmod 600 "$CFG"

echo "5/7 Создаю постоянный Tauri signing key…"
if [[ ! -s "$TAURI_KEY" || ! -s "$TAURI_PUB" ]]; then
  rm -f "$TAURI_KEY" "$TAURI_PUB"
  npx --yes @tauri-apps/cli@2.10.1 signer generate -w "$TAURI_KEY" -p '' --ci || fail "Tauri signer generate failed"
fi
chmod 600 "$TAURI_KEY"; [[ -s "$TAURI_PUB" ]] || fail "Tauri public key отсутствует"
PUBLIC_KEY="$(tr -d '\r\n' < "$TAURI_PUB")"

echo "6/7 Сохраняю безопасный VPS bootstrap в GitHub…"
BOOT="$TMP/bootstrap.json"
python3 - "$BOOT" "$BASE_URL" "$PUBLIC_KEY" <<'PY'
import json,sys,datetime
json.dump({'provider':'self-hosted-vps','baseUrl':sys.argv[2],'endpoint':sys.argv[2]+'/v1/update/{{target}}/{{arch}}/{{current_version}}','pubkey':sys.argv[3],'buildTransport':'macos-launchagent-ssh-no-actions','storage':'own-vps','updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()},open(sys.argv[1],'w'),indent=2)
PY
SHA="$(gh api "/repos/$REPO/contents/updates/vps/bootstrap.json?ref=$BRANCH" --jq .sha 2>/dev/null || true)"
python3 - "$BOOT" "$TMP/payload.json" "$BRANCH" "$SHA" <<'PY'
import json,sys,base64,pathlib
src,out,branch,sha=sys.argv[1:]
p={'message':'Configure ENDLUME private VPS updater','branch':branch,'content':base64.b64encode(pathlib.Path(src).read_bytes()).decode()}
if sha:p['sha']=sha
json.dump(p,open(out,'w'))
PY
gh api --method PUT "/repos/$REPO/contents/updates/vps/bootstrap.json" --input "$TMP/payload.json" >/dev/null || fail "не удалось сохранить VPS bootstrap"

echo "7/7 Устанавливаю локальный Release Agent…"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/scripts/endlume-release-agent-vps-macos.sh?ref=$BRANCH" > "$AGENT" || fail "не удалось скачать agent"
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

cat > "$HOME/Desktop/ENDLUME-VPS-UPDATE-SERVER.txt" <<EOF
ENDLUME PRIVATE VPS UPDATE SERVER
Endpoint: $BASE_URL
VPS: $VPS_USER@$VPS_HOST:$VPS_PORT
Signing public key: $PUBLIC_KEY
Signing private key: $TAURI_KEY (НЕ ПЕРЕДАВАТЬ)
SSH deploy key: $SSH_KEY (НЕ ПЕРЕДАВАТЬ)
GitHub Actions: НЕ ИСПОЛЬЗУЮТСЯ
Cloudflare: НЕ ИСПОЛЬЗУЕТСЯ
EOF

echo
echo "✅ ENDLUME VPS update infrastructure ready"
echo "✅ Без карт / Cloudflare / GitHub Actions / GitHub Releases"
echo "✅ HTTPS: $BASE_URL"
echo "✅ Release Agent проверяет новые версии раз в 60 секунд"
echo "✅ build-request пока выключен — ничего само не собирается"
echo
echo "Теперь напиши в ChatGPT: VPS updater готов"
