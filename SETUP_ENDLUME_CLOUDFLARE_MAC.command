#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
BUCKET="endlume-private-updates"
KEYDIR="$HOME/.endlume-updater"
KEY="$KEYDIR/endlume.key"
PUB="$KEY.pub"
HMAC_FILE="$KEYDIR/cloudflare-download-hmac.txt"
AGENT_DIR="$HOME/.endlume-release-agent"
AGENT="$AGENT_DIR/agent.sh"
PLIST="$HOME/Library/LaunchAgents/studio.endlume.release-agent.plist"
TMP="$(mktemp -d /tmp/endlume-cloudflare-setup.XXXXXX)"
LOG="$HOME/Desktop/ENDLUME-Cloudflare-Setup.log"
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
exec > >(tee "$LOG") 2>&1
fail(){ echo; echo "❌ $1"; echo "Лог: $LOG"; exit 1; }

WRANGLER=(npx --yes wrangler@4)

echo "ENDLUME • Cloudflare R2 + local Mac Release Agent setup • FIX4"
echo
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"
mkdir -p "$KEYDIR" "$AGENT_DIR" "$HOME/Library/LaunchAgents"
chmod 700 "$KEYDIR" "$AGENT_DIR" || true

node_runtime_ok(){
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 && \
  node -e 'process.stdout.write(process.version)' >/dev/null 2>&1 && npm --version >/dev/null 2>&1
}
if ! node_runtime_ok; then
  echo "0/8 Восстанавливаю Homebrew Node runtime…"
  BREW=""
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do [[ -x "$p" ]] && BREW="$p" && break; done
  [[ -n "$BREW" ]] || fail "Node/npm повреждены, а Homebrew не найден"
  "$BREW" update || true
  "$BREW" reinstall simdutf || fail "не удалось переустановить simdutf"
  "$BREW" reinstall merve || fail "не удалось переустановить merve"
  hash -r
  if ! node_runtime_ok; then
    "$BREW" reinstall node || fail "не удалось переустановить Node.js"
    hash -r
  fi
fi
node_runtime_ok || fail "Node/npm всё ещё не запускаются после автоматического восстановления"
echo "✅ Node $(node -v) • npm $(npm -v)"

echo "1/8 Проверяю Cloudflare CLI и получаю Worker…"
"${WRANGLER[@]}" --version >/dev/null || fail "Wrangler не запускается"
mkdir -p "$TMP/worker/src"
for f in infra/cloudflare-update/src/index.js infra/cloudflare-update/wrangler.toml; do
  out="$TMP/worker/${f#infra/cloudflare-update/}"
  mkdir -p "$(dirname "$out")"
  gh api -H "Accept: application/vnd.github.raw+json" "/repos/$REPO/contents/$f?ref=$BRANCH" > "$out" || fail "не удалось скачать $f"
done
cd "$TMP/worker"

echo "2/8 Проверяю реальную авторизацию Cloudflare…"
WHO="$(${WRANGLER[@]} whoami 2>&1 || true)"
if echo "$WHO" | grep -qiE 'not authenticated|not logged in|please run.*wrangler login'; then
  echo "Cloudflare ещё не авторизован. Сейчас откроется браузер."
  "${WRANGLER[@]}" login || fail "Cloudflare login не завершён"
  WHO="$(${WRANGLER[@]} whoami 2>&1 || true)"
fi
if echo "$WHO" | grep -qiE 'not authenticated|not logged in|please run.*wrangler login'; then
  echo "$WHO"
  fail "Cloudflare по-прежнему не подтверждает авторизацию"
fi
if [[ -z "${WHO//[[:space:]]/}" ]]; then fail "Wrangler whoami вернул пустой ответ"; fi
echo "$WHO"
echo "✅ Cloudflare авторизация подтверждена"

echo "3/8 Проверяю R2 subscription…"
R2_LIST_FILE="$TMP/r2-list.txt"
r2_ready(){
  if "${WRANGLER[@]}" r2 bucket list >"$R2_LIST_FILE" 2>&1; then
    if ! grep -qiE 'not authenticated|subscription.*required|complete.*checkout|enable.*r2' "$R2_LIST_FILE"; then return 0; fi
  fi
  return 1
}
if ! r2_ready; then
  echo
  echo "Cloudflare аккаунт авторизован, но R2 ещё не подключён."
  echo "Открываю официальный R2 Overview. Заверши подключение R2/checkout в браузере."
  echo "После этого ничего в Terminal нажимать не нужно — я сам проверяю каждые 5 секунд."
  /usr/bin/open 'https://dash.cloudflare.com/?to=/:account/r2/overview' >/dev/null 2>&1 || true
  READY=0
  for i in $(seq 1 240); do
    /bin/sleep 5
    if r2_ready; then READY=1; break; fi
    if (( i % 12 == 0 )); then echo "Жду активацию R2… $((i*5)) сек"; fi
  done
  [[ "$READY" == "1" ]] || { cat "$R2_LIST_FILE" || true; fail "R2 не активирован за 20 минут"; }
fi
echo "✅ R2 доступен"

echo "4/8 Проверяю приватный bucket…"
R2_LIST="$(cat "$R2_LIST_FILE" 2>/dev/null || true)"
if ! echo "$R2_LIST" | grep -Fq "$BUCKET"; then
  "${WRANGLER[@]}" r2 bucket create "$BUCKET" || fail "не удалось создать R2 bucket $BUCKET"
  "${WRANGLER[@]}" r2 bucket list >"$R2_LIST_FILE" 2>&1 || fail "не удалось проверить список R2 buckets"
fi
grep -Fq "$BUCKET" "$R2_LIST_FILE" || fail "R2 bucket $BUCKET отсутствует после создания"
echo "✅ Private R2 bucket: $BUCKET"

echo "5/8 Деплою приватный R2 Update API…"
DEPLOY_LOG="$TMP/wrangler-deploy.log"
"${WRANGLER[@]}" deploy 2>&1 | tee "$DEPLOY_LOG" || fail "первичный Worker deploy завершился ошибкой"
WORKER_URL="$(grep -Eo 'https://[A-Za-z0-9._-]+\.workers\.dev' "$DEPLOY_LOG" | tail -1 || true)"
[[ -n "$WORKER_URL" ]] || fail "не удалось определить workers.dev URL из вывода Wrangler"
if [[ ! -s "$HMAC_FILE" ]]; then
  /usr/bin/openssl rand -hex 32 > "$HMAC_FILE"
  chmod 600 "$HMAC_FILE"
fi
cat "$HMAC_FILE" | "${WRANGLER[@]}" secret put DOWNLOAD_HMAC_SECRET >/dev/null || fail "не удалось установить Worker secret"
"${WRANGLER[@]}" deploy >/dev/null || fail "повторный Worker deploy после secret завершился ошибкой"
for _ in $(seq 1 20); do
  if /usr/bin/curl -fsS "$WORKER_URL/health" >/dev/null 2>&1; then break; fi
  /bin/sleep 2
done
/usr/bin/curl -fsS "$WORKER_URL/health" >/dev/null || fail "Worker /health недоступен после deploy"
echo "✅ Worker: $WORKER_URL"

echo "6/8 Создаю постоянный ключ подписи Tauri updater…"
if [[ ! -s "$KEY" || ! -s "$PUB" ]]; then
  rm -f "$KEY" "$PUB"
  npx --yes @tauri-apps/cli@2.10.1 signer generate -w "$KEY" -p "" --ci || fail "Tauri signer generate завершился ошибкой"
  chmod 600 "$KEY"
fi
[[ -s "$KEY" ]] || fail "private updater key отсутствует: $KEY"
[[ -s "$PUB" ]] || fail "public updater key отсутствует: $PUB"
PUBLIC_KEY="$(tr -d '\r\n' < "$PUB")"
[[ ${#PUBLIC_KEY} -gt 40 ]] || fail "public updater key выглядит некорректно"
echo "✅ Tauri signing key готов"

echo "7/8 Сохраняю безопасный bootstrap в GitHub…"
BOOT="$TMP/bootstrap.json"
python3 - "$BOOT" "$WORKER_URL" "$PUBLIC_KEY" <<'PY'
import json,sys,datetime
json.dump({
  'provider':'cloudflare-r2-worker',
  'workerUrl':sys.argv[2],
  'endpoint':sys.argv[2]+'/v1/update/{{target}}/{{arch}}/{{current_version}}',
  'pubkey':sys.argv[3],
  'bucket':'endlume-private-updates',
  'buildTransport':'macos-launchagent-github-api-no-actions',
  'updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()
},open(sys.argv[1],'w'),indent=2)
PY
SHA="$(gh api "/repos/$REPO/contents/updates/cloudflare/bootstrap.json?ref=$BRANCH" --jq .sha 2>/dev/null || true)"
python3 - "$BOOT" "$TMP/payload.json" "$BRANCH" "$SHA" <<'PY'
import json,sys,base64,pathlib
src,out,branch,sha=sys.argv[1:]
p={'message':'Configure ENDLUME Cloudflare updater bootstrap','branch':branch,'content':base64.b64encode(pathlib.Path(src).read_bytes()).decode()}
if sha:p['sha']=sha
json.dump(p,open(out,'w'))
PY
gh api --method PUT "/repos/$REPO/contents/updates/cloudflare/bootstrap.json" --input "$TMP/payload.json" >/dev/null || fail "не удалось сохранить bootstrap.json"
echo "✅ bootstrap.json сохранён"

echo "8/8 Устанавливаю локальный Release Agent без GitHub Actions…"
gh api -H "Accept: application/vnd.github.raw+json" "/repos/$REPO/contents/scripts/endlume-release-agent-macos.sh?ref=$BRANCH" > "$AGENT" || fail "не удалось скачать Release Agent"
[[ -s "$AGENT" ]] || fail "Release Agent пуст"
chmod 755 "$AGENT"
/bin/bash -n "$AGENT" || fail "Release Agent не прошёл bash syntax"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>studio.endlume.release-agent</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>$AGENT</string></array>
<key>RunAtLoad</key><true/><key>StartInterval</key><integer>60</integer><key>ProcessType</key><string>Background</string>
<key>EnvironmentVariables</key><dict><key>HOME</key><string>$HOME</string><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
<key>StandardOutPath</key><string>$AGENT_DIR/launchd.out.log</string><key>StandardErrorPath</key><string>$AGENT_DIR/launchd.err.log</string>
</dict></plist>
EOF
/usr/bin/plutil -lint "$PLIST" >/dev/null || fail "LaunchAgent plist некорректен"
UID_NOW="$(id -u)"
/bin/launchctl bootout "gui/$UID_NOW" "$PLIST" >/dev/null 2>&1 || true
/bin/launchctl bootstrap "gui/$UID_NOW" "$PLIST" || fail "не удалось запустить ENDLUME Release Agent"
/bin/launchctl kickstart -k "gui/$UID_NOW/studio.endlume.release-agent" >/dev/null 2>&1 || true

cat > "$HOME/Desktop/ENDLUME-UPDATE-SERVER.txt" <<EOF
ENDLUME Cloudflare Update Server
Worker: $WORKER_URL
Bucket: $BUCKET
Public updater key: $PUBLIC_KEY
Private signing key: $KEY (НЕ ПЕРЕДАВАТЬ НИКОМУ)
Release Agent: $AGENT
LaunchAgent: $PLIST
GitHub Actions: НЕ ИСПОЛЬЗУЮТСЯ
EOF

echo
echo "✅ ENDLUME Cloudflare infrastructure ready"
echo "✅ R2 bucket приватный"
echo "✅ Worker выдаёт временные download URL на 10 минут"
echo "✅ Tauri private signing key хранится только на этом Mac"
echo "✅ Local Release Agent проверяет новые версии раз в 60 секунд"
echo "✅ GitHub Actions и их лимиты больше не используются"
echo "✅ Bootstrap сохранён в updates/cloudflare/bootstrap.json"
echo
echo "Теперь напиши в ChatGPT: Cloudflare setup готов."
