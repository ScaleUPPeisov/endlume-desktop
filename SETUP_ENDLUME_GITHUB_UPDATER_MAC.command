#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
HOST_REPO="ScaleUPPeisov/scaleup-site"
TAG="endlume-stable"
KEYDIR="$HOME/.endlume-updater"
KEY="$KEYDIR/endlume.key"
PUB="$KEY.pub"
AGENT_DIR="$HOME/.endlume-github-release-agent"
AGENT="$AGENT_DIR/agent.sh"
PLIST="$HOME/Library/LaunchAgents/studio.endlume.github-release-agent.plist"
TMP="$(mktemp -d /tmp/endlume-github-updater.XXXXXX)"
LOG="$HOME/Desktop/ENDLUME-GitHub-Updater-Setup.log"
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
exec > >(tee "$LOG") 2>&1
fail(){ echo; echo "❌ $1"; echo "Лог: $LOG"; exit 1; }

echo "ENDLUME • SIMPLE GITHUB UPDATER"
echo "Без VPS • без JustHost • без IP • без SSH • без Cloudflare"
echo "Без GitHub Actions • без GitHub Actions minutes"
echo
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"
command -v npx >/dev/null 2>&1 || fail "npx не найден"
command -v python3 >/dev/null 2>&1 || fail "python3 не найден"
mkdir -p "$KEYDIR" "$AGENT_DIR" "$HOME/Library/LaunchAgents"
chmod 700 "$KEYDIR" "$AGENT_DIR" || true

echo "1/4 Создаю постоянный ключ подписи обновлений…"
if [[ ! -s "$KEY" || ! -s "$PUB" ]]; then
  rm -f "$KEY" "$PUB"
  npx --yes @tauri-apps/cli@2.10.1 signer generate -w "$KEY" --ci || fail "Tauri signer generate failed"
fi
chmod 600 "$KEY"; chmod 644 "$PUB"
PUBLIC_KEY="$(tr -d '\r\n' < "$PUB")"
[[ -n "$PUBLIC_KEY" ]] || fail "public signing key empty"
echo "✅ Подпись готова"

echo "2/4 Создаю постоянный публичный канал ENDLUME…"
if ! gh release view "$TAG" --repo "$HOST_REPO" >/dev/null 2>&1; then
  gh release create "$TAG" --repo "$HOST_REPO" --title "ENDLUME Stable Updates" --notes "Signed update channel. No GitHub Actions are used." || fail "не удалось создать update channel"
fi
ENDPOINT="https://github.com/$HOST_REPO/releases/download/$TAG/latest.json"
echo "✅ $ENDPOINT"

echo "3/4 Сохраняю updater bootstrap в приватный исходный репозиторий…"
BOOT="$TMP/bootstrap.json"
python3 - "$BOOT" "$ENDPOINT" "$PUBLIC_KEY" <<'PY'
import json,sys,datetime
json.dump({
  'provider':'github-static-release',
  'hostRepo':'ScaleUPPeisov/scaleup-site',
  'tag':'endlume-stable',
  'endpoint':sys.argv[2],
  'pubkey':sys.argv[3],
  'actions':False,
  'releasesMode':'single-static-channel',
  'platforms':['darwin-aarch64','windows-x86_64'],
  'updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()
},open(sys.argv[1],'w'),ensure_ascii=False,indent=2)
PY
SHA="$(gh api "/repos/$REPO/contents/updates/github/bootstrap.json?ref=$BRANCH" --jq .sha 2>/dev/null || true)"
python3 - "$BOOT" "$TMP/payload.json" "$BRANCH" "$SHA" <<'PY'
import json,sys,base64,pathlib
src,out,branch,sha=sys.argv[1:]
p={'message':'Configure simple GitHub updater bootstrap','branch':branch,'content':base64.b64encode(pathlib.Path(src).read_bytes()).decode()}
if sha:p['sha']=sha
json.dump(p,open(out,'w'))
PY
gh api --method PUT "/repos/$REPO/contents/updates/github/bootstrap.json" --input "$TMP/payload.json" >/dev/null || fail "bootstrap save failed"
echo "✅ Bootstrap сохранён"

echo "4/4 Устанавливаю локальный release-agent…"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/scripts/endlume-github-release-agent-macos.sh?ref=$BRANCH" > "$AGENT" || fail "agent download failed"
chmod 755 "$AGENT"; /bin/bash -n "$AGENT" || fail "agent syntax error"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>studio.endlume.github-release-agent</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>$AGENT</string></array>
<key>RunAtLoad</key><true/>
<key>StartInterval</key><integer>60</integer>
<key>ProcessType</key><string>Background</string>
<key>EnvironmentVariables</key><dict><key>HOME</key><string>$HOME</string><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
<key>StandardOutPath</key><string>$AGENT_DIR/launchd.out.log</string>
<key>StandardErrorPath</key><string>$AGENT_DIR/launchd.err.log</string>
</dict></plist>
EOF
plutil -lint "$PLIST" >/dev/null || fail "LaunchAgent plist invalid"
UID_NOW="$(id -u)"
launchctl bootout "gui/$UID_NOW" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_NOW" "$PLIST" || fail "LaunchAgent bootstrap failed"
launchctl kickstart -k "gui/$UID_NOW/studio.endlume.github-release-agent" >/dev/null 2>&1 || true

cat > "$HOME/Desktop/ENDLUME-UPDATE-CHANNEL.txt" <<EOF
ENDLUME SIMPLE UPDATE CHANNEL
Endpoint: $ENDPOINT
Source code: private
Update packages: public, cryptographically signed
GitHub Actions: NOT USED
VPS/JustHost/Cloudflare: NOT USED
Signing private key: $KEY (DO NOT SHARE)
EOF

echo
echo "✅ ENDLUME SIMPLE UPDATER READY"
echo "✅ IP/SSH/пароли/VPS больше не нужны"
echo "✅ GitHub Actions не используются"
echo "✅ Mac release-agent установлен"
echo "✅ build-request выключен — сборка сама сейчас не стартует"
