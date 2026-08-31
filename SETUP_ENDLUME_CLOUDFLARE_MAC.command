#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
BUCKET="endlume-private-updates"
KEYDIR="$HOME/.endlume-updater"
TOKEN_FILE="$KEYDIR/cloudflare-api-token.txt"
ACCOUNT_FILE="$KEYDIR/cloudflare-account-id.txt"
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

echo "ENDLUME • Cloudflare R2 + local Mac Release Agent setup • TOKEN AUTH"
echo "Без OAuth • без localhost callback • без GitHub Actions"
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
  echo "0/9 Восстанавливаю Homebrew Node runtime…"
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

echo "1/9 Проверяю Wrangler…"
npx --yes wrangler@4 --version >/dev/null || fail "Wrangler не запускается"

token_valid(){
  local token="$1" out="$TMP/token-verify.json"
  [[ -n "$token" ]] || return 1
  /usr/bin/curl -fsS -H "Authorization: Bearer $token" \
    'https://api.cloudflare.com/client/v4/user/tokens/verify' -o "$out" 2>/dev/null || return 1
  python3 - "$out" <<'PY' >/dev/null 2>&1
import json,sys
j=json.load(open(sys.argv[1]))
raise SystemExit(0 if j.get('success') and (j.get('result') or {}).get('status')=='active' else 1)
PY
}

TOKEN=""
if [[ -s "$TOKEN_FILE" ]]; then TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"; fi
if ! token_valid "$TOKEN"; then
  rm -f "$TOKEN_FILE"
  echo
  echo "2/9 Нужен один постоянный Cloudflare API Token. OAuth/localhost больше НЕ используется."
  echo "Сейчас открою Cloudflare → API Tokens. Создай Custom Token со следующими правами:"
  echo "  Account → Account Settings → Read"
  echo "  Account → Workers Scripts → Edit"
  echo "  Account → Workers R2 Storage → Edit"
  echo "  User → User Details → Read"
  echo "  User → Memberships → Read"
  echo "Resources: Include → твой Cloudflare account."
  echo
  /usr/bin/open 'https://dash.cloudflare.com/profile/api-tokens' >/dev/null 2>&1 || true
  while true; do
    printf 'Вставь созданный Cloudflare API Token сюда и нажми Enter: '
    IFS= read -r -s TOKEN
    echo
    TOKEN="$(printf '%s' "$TOKEN" | tr -d '\r\n ')"
    if token_valid "$TOKEN"; then break; fi
    echo "❌ Этот token Cloudflare не подтверждает как active. Проверь token и вставь снова."
  done
  printf '%s\n' "$TOKEN" > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
fi
export CLOUDFLARE_API_TOKEN="$TOKEN"
echo "✅ Cloudflare API Token подтверждён"

echo "3/9 Определяю Cloudflare Account ID…"
ACCOUNTS="$TMP/accounts.json"
/usr/bin/curl -fsS -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  'https://api.cloudflare.com/client/v4/accounts?per_page=50' -o "$ACCOUNTS" \
  || fail "не удалось получить список Cloudflare accounts — проверь Account Settings Read / Memberships Read"
python3 - "$ACCOUNTS" "$TMP/accounts.tsv" <<'PY'
import json,sys
j=json.load(open(sys.argv[1])); rows=j.get('result') or []
if not j.get('success') or not rows: raise SystemExit(2)
with open(sys.argv[2],'w') as f:
  for i,a in enumerate(rows,1): f.write(f"{i}\t{a.get('id','')}\t{a.get('name','')}\n")
PY
case "$?" in 0) ;; *) fail "Cloudflare token не видит account. Добавь Account Settings Read и Memberships Read" ;; esac
COUNT="$(wc -l < "$TMP/accounts.tsv" | tr -d ' ')"
if [[ "$COUNT" == "1" ]]; then
  ACCOUNT_ID="$(cut -f2 "$TMP/accounts.tsv")"
  ACCOUNT_NAME="$(cut -f3- "$TMP/accounts.tsv")"
else
  echo "Найдено несколько Cloudflare accounts:"
  cat "$TMP/accounts.tsv"
  while true; do
    printf 'Номер account для ENDLUME: '; IFS= read -r CHOICE
    ACCOUNT_ID="$(awk -F '\t' -v n="$CHOICE" '$1==n{print $2}' "$TMP/accounts.tsv")"
    ACCOUNT_NAME="$(awk -F '\t' -v n="$CHOICE" '$1==n{$1=$2="";sub(/^\t\t/,"");print}' "$TMP/accounts.tsv")"
    [[ -n "$ACCOUNT_ID" ]] && break
  done
fi
printf '%s\n' "$ACCOUNT_ID" > "$ACCOUNT_FILE"; chmod 600 "$ACCOUNT_FILE"
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT_ID"
echo "✅ Account: $ACCOUNT_NAME • $ACCOUNT_ID"

# From this point all Wrangler calls are non-interactive API-token auth.
WRANGLER=(npx --yes wrangler@4)
echo "4/9 Получаю Worker и проверяю token через Wrangler…"
WHO="$(${WRANGLER[@]} whoami 2>&1 || true)"
if echo "$WHO" | grep -qiE 'not authenticated|not logged in|invalid.*token|authentication error'; then echo "$WHO"; fail "Wrangler не принял API Token"; fi
mkdir -p "$TMP/worker/src"
for f in infra/cloudflare-update/src/index.js infra/cloudflare-update/wrangler.toml; do
  out="$TMP/worker/${f#infra/cloudflare-update/}"
  mkdir -p "$(dirname "$out")"
  gh api -H "Accept: application/vnd.github.raw+json" "/repos/$REPO/contents/$f?ref=$BRANCH" > "$out" || fail "не удалось скачать $f"
done
cd "$TMP/worker"

echo "5/9 Проверяю R2 subscription и private bucket…"
R2_LIST_FILE="$TMP/r2-list.txt"
r2_ready(){ "${WRANGLER[@]}" r2 bucket list >"$R2_LIST_FILE" 2>&1; }
if ! r2_ready; then
  echo "R2 ещё не активирован для этого account. Открываю R2 Overview."
  echo "В браузере один раз подключи R2/заверши checkout. Terminal сам продолжит после активации."
  /usr/bin/open "https://dash.cloudflare.com/$ACCOUNT_ID/r2" >/dev/null 2>&1 || true
  READY=0
  for i in $(seq 1 240); do
    /bin/sleep 5
    if r2_ready; then READY=1; break; fi
    if (( i % 12 == 0 )); then echo "Жду активацию R2… $((i*5)) сек"; fi
  done
  [[ "$READY" == "1" ]] || { cat "$R2_LIST_FILE" || true; fail "R2 не активирован за 20 минут"; }
fi
if ! grep -Fq "$BUCKET" "$R2_LIST_FILE"; then
  "${WRANGLER[@]}" r2 bucket create "$BUCKET" || fail "не удалось создать R2 bucket $BUCKET"
  "${WRANGLER[@]}" r2 bucket list >"$R2_LIST_FILE" 2>&1 || fail "не удалось проверить список R2 buckets"
fi
grep -Fq "$BUCKET" "$R2_LIST_FILE" || fail "R2 bucket $BUCKET отсутствует после создания"
echo "✅ Private R2 bucket: $BUCKET"

echo "6/9 Деплою ENDLUME Update Worker…"
DEPLOY_LOG="$TMP/wrangler-deploy.log"
set +e
"${WRANGLER[@]}" deploy 2>&1 | tee "$DEPLOY_LOG"
DEPLOY_CODE=${PIPESTATUS[0]}
set -e
if [[ "$DEPLOY_CODE" != "0" ]]; then
  if grep -qiE 'workers.dev.*subdomain|configure.*subdomain|register.*subdomain' "$DEPLOY_LOG"; then
    echo "Cloudflare просит один раз настроить workers.dev subdomain. Открываю Workers & Pages."
    /usr/bin/open "https://dash.cloudflare.com/$ACCOUNT_ID/workers-and-pages" >/dev/null 2>&1 || true
    echo "Создай/подтверди workers.dev subdomain, затем вернись сюда и нажми Enter."
    IFS= read -r _
    "${WRANGLER[@]}" deploy 2>&1 | tee "$DEPLOY_LOG" || fail "Worker deploy не завершился после настройки workers.dev"
  else
    fail "Worker deploy завершился ошибкой"
  fi
fi
WORKER_URL="$(grep -Eo 'https://[A-Za-z0-9._-]+\.workers\.dev' "$DEPLOY_LOG" | tail -1 || true)"
[[ -n "$WORKER_URL" ]] || fail "не удалось определить workers.dev URL"
if [[ ! -s "$HMAC_FILE" ]]; then /usr/bin/openssl rand -hex 32 > "$HMAC_FILE"; chmod 600 "$HMAC_FILE"; fi
cat "$HMAC_FILE" | "${WRANGLER[@]}" secret put DOWNLOAD_HMAC_SECRET >/dev/null || fail "не удалось установить Worker secret"
"${WRANGLER[@]}" deploy >/dev/null || fail "повторный Worker deploy после secret завершился ошибкой"
for _ in $(seq 1 30); do /usr/bin/curl -fsS "$WORKER_URL/health" >/dev/null 2>&1 && break; /bin/sleep 2; done
/usr/bin/curl -fsS "$WORKER_URL/health" >/dev/null || fail "Worker /health недоступен после deploy"
echo "✅ Worker: $WORKER_URL"

echo "7/9 Создаю постоянный Tauri signing key…"
if [[ ! -s "$KEY" || ! -s "$PUB" ]]; then
  rm -f "$KEY" "$PUB"
  npx --yes @tauri-apps/cli@2.10.1 signer generate -w "$KEY" -p "" --ci || fail "Tauri signer generate завершился ошибкой"
  chmod 600 "$KEY"
fi
[[ -s "$KEY" && -s "$PUB" ]] || fail "Tauri updater key pair не создан"
PUBLIC_KEY="$(tr -d '\r\n' < "$PUB")"
[[ ${#PUBLIC_KEY} -gt 40 ]] || fail "public updater key выглядит некорректно"
echo "✅ Tauri signing key готов"

echo "8/9 Сохраняю безопасный bootstrap в GitHub…"
BOOT="$TMP/bootstrap.json"
python3 - "$BOOT" "$WORKER_URL" "$PUBLIC_KEY" <<'PY'
import json,sys,datetime
json.dump({'provider':'cloudflare-r2-worker','workerUrl':sys.argv[2],'endpoint':sys.argv[2]+'/v1/update/{{target}}/{{arch}}/{{current_version}}','pubkey':sys.argv[3],'bucket':'endlume-private-updates','buildTransport':'macos-launchagent-github-api-no-actions','auth':'cloudflare-api-token-local-only','updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()},open(sys.argv[1],'w'),indent=2)
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

echo "9/9 Устанавливаю Local Release Agent без GitHub Actions…"
gh api -H "Accept: application/vnd.github.raw+json" "/repos/$REPO/contents/scripts/endlume-release-agent-macos.sh?ref=$BRANCH" > "$AGENT" || fail "не удалось скачать Release Agent"
[[ -s "$AGENT" ]] || fail "Release Agent пуст"
chmod 755 "$AGENT"; /bin/bash -n "$AGENT" || fail "Release Agent не прошёл bash syntax"
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
UID_NOW="$(id -u)"; /bin/launchctl bootout "gui/$UID_NOW" "$PLIST" >/dev/null 2>&1 || true
/bin/launchctl bootstrap "gui/$UID_NOW" "$PLIST" || fail "не удалось запустить ENDLUME Release Agent"
/bin/launchctl kickstart -k "gui/$UID_NOW/studio.endlume.release-agent" >/dev/null 2>&1 || true

cat > "$HOME/Desktop/ENDLUME-UPDATE-SERVER.txt" <<EOF
ENDLUME Cloudflare Update Server
Worker: $WORKER_URL
Bucket: $BUCKET
Cloudflare Account ID: $ACCOUNT_ID
Cloudflare API Token: $TOKEN_FILE (LOCAL ONLY)
Public updater key: $PUBLIC_KEY
Private signing key: $KEY (LOCAL ONLY)
Release Agent: $AGENT
GitHub Actions: НЕ ИСПОЛЬЗУЮТСЯ
EOF

echo
echo "✅ ENDLUME Cloudflare infrastructure ready"
echo "✅ OAuth/localhost полностью исключены"
echo "✅ Cloudflare API Token хранится только локально"
echo "✅ R2 bucket приватный"
echo "✅ Worker выдаёт временные download URL на 10 минут"
echo "✅ Tauri private signing key хранится только на этом Mac"
echo "✅ Local Release Agent проверяет новые версии раз в 60 секунд"
echo "✅ GitHub Actions и их лимиты не используются"
echo "✅ Bootstrap сохранён в updates/cloudflare/bootstrap.json"
echo
echo "Теперь напиши в ChatGPT: Cloudflare setup готов."
