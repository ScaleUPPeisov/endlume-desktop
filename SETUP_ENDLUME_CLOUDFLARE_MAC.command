#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
BUCKET="endlume-private-updates"
KEYDIR="$HOME/.endlume-updater"
KEY="$KEYDIR/endlume.key"
PUB="$KEYDIR/endlume.pub"
HMAC_FILE="$KEYDIR/cloudflare-download-hmac.txt"
RUNNER_DIR="$HOME/.endlume-github-runner"
TMP="$(mktemp -d /tmp/endlume-cloudflare-setup.XXXXXX)"
LOG="$HOME/Desktop/ENDLUME-Cloudflare-Setup.log"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
exec > >(tee "$LOG") 2>&1
fail(){ echo; echo "❌ $1"; echo "Лог: $LOG"; exit 1; }

echo "ENDLUME • Cloudflare R2 + self-hosted Mac setup"
echo
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"
command -v node >/dev/null 2>&1 || fail "Node.js не найден"
command -v npm >/dev/null 2>&1 || fail "npm не найден"
mkdir -p "$KEYDIR"; chmod 700 "$KEYDIR" || true

echo "1/6 Получаю Cloudflare Worker из приватного репозитория…"
mkdir -p "$TMP/worker/src"
for f in infra/cloudflare-update/src/index.js infra/cloudflare-update/wrangler.toml infra/cloudflare-update/package.json; do
  out="$TMP/worker/${f#infra/cloudflare-update/}"
  mkdir -p "$(dirname "$out")"
  gh api -H "Accept: application/vnd.github.raw+json" "/repos/$REPO/contents/$f?ref=$BRANCH" > "$out" || fail "не удалось скачать $f"
done
cd "$TMP/worker"
npm install --no-audit --no-fund

echo "2/6 Авторизую Cloudflare…"
if ! npx wrangler whoami >/dev/null 2>&1; then
  echo "Сейчас откроется браузер Cloudflare. Войди или создай аккаунт и разреши Wrangler."
  npx wrangler login || fail "Cloudflare login не завершён"
fi
npx wrangler r2 bucket create "$BUCKET" >/dev/null 2>&1 || true
if [[ ! -s "$HMAC_FILE" ]]; then
  /usr/bin/openssl rand -hex 32 > "$HMAC_FILE"
  chmod 600 "$HMAC_FILE"
fi
cat "$HMAC_FILE" | npx wrangler secret put DOWNLOAD_HMAC_SECRET >/dev/null || fail "не удалось установить Worker secret"

echo "3/6 Деплою приватный R2 Update API…"
DEPLOY_LOG="$TMP/wrangler-deploy.log"
npx wrangler deploy 2>&1 | tee "$DEPLOY_LOG" || fail "Worker deploy завершился ошибкой"
WORKER_URL="$(grep -Eo 'https://[A-Za-z0-9._-]+\.workers\.dev' "$DEPLOY_LOG" | tail -1 || true)"
[[ -n "$WORKER_URL" ]] || fail "не удалось определить workers.dev URL из вывода Wrangler"
/usr/bin/curl -fsS "$WORKER_URL/health" >/dev/null || fail "Worker /health недоступен"
echo "✅ Worker: $WORKER_URL"

echo "4/6 Создаю постоянный ключ подписи Tauri updater…"
if [[ ! -s "$KEY" ]]; then
  SIGN_LOG="$TMP/tauri-signer.log"
  npx --yes @tauri-apps/cli@2.10.1 signer generate -w "$KEY" -p "" 2>&1 | tee "$SIGN_LOG" || fail "Tauri signer generate завершился ошибкой"
  chmod 600 "$KEY"
  python3 - "$SIGN_LOG" "$PUB" <<'PY'
import re,sys,pathlib
raw=pathlib.Path(sys.argv[1]).read_text(errors='ignore')
raw=re.sub(r'\x1b\[[0-9;]*m','',raw)
m=re.findall(r'Public:\s*(\S+)',raw)
if not m: raise SystemExit('Public key not found in tauri signer output')
pathlib.Path(sys.argv[2]).write_text(m[-1].strip()+"\n")
PY
fi
[[ -s "$PUB" ]] || fail "public updater key отсутствует: $PUB"
PUBLIC_KEY="$(tr -d '\r\n' < "$PUB")"
[[ ${#PUBLIC_KEY} -gt 40 ]] || fail "public updater key выглядит некорректно"

echo "5/6 Сохраняю безопасный bootstrap в GitHub…"
BOOT="$TMP/bootstrap.json"
python3 - "$BOOT" "$WORKER_URL" "$PUBLIC_KEY" <<'PY'
import json,sys,datetime
json.dump({'provider':'cloudflare-r2-worker','workerUrl':sys.argv[2],'endpoint':sys.argv[2]+'/v1/update/{{target}}/{{arch}}/{{current_version}}','pubkey':sys.argv[3],'bucket':'endlume-private-updates','updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()},open(sys.argv[1],'w'),indent=2)
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

echo "6/6 Регистрирую этот Mac как бесплатный self-hosted runner…"
if [[ ! -f "$RUNNER_DIR/.runner" ]]; then
  mkdir -p "$RUNNER_DIR"
  RUNNER_URL="$(gh api repos/actions/runner/releases/latest --jq '.assets[].browser_download_url' | grep -E '/actions-runner-osx-arm64-[^/]+\.tar\.gz$' | head -1 || true)"
  [[ -n "$RUNNER_URL" ]] || fail "не удалось найти actions-runner osx-arm64"
  /usr/bin/curl -fL "$RUNNER_URL" -o "$TMP/runner.tar.gz" || fail "не удалось скачать GitHub self-hosted runner"
  tar -xzf "$TMP/runner.tar.gz" -C "$RUNNER_DIR"
  TOKEN="$(gh api --method POST "/repos/$REPO/actions/runners/registration-token" --jq .token)"
  [[ -n "$TOKEN" ]] || fail "не удалось получить registration token"
  NAME="ENDLUME-Mac-$(/usr/sbin/scutil --get ComputerName 2>/dev/null | tr ' /' '--' || echo ARM64)"
  cd "$RUNNER_DIR"
  ./config.sh --url "https://github.com/$REPO" --token "$TOKEN" --name "$NAME" --labels "endlume,macos,arm64" --unattended --replace --work _work || fail "runner config failed"
  ./svc.sh install || true
  ./svc.sh start || { nohup ./run.sh > "$KEYDIR/runner.log" 2>&1 & }
else
  cd "$RUNNER_DIR"
  ./svc.sh start >/dev/null 2>&1 || true
fi

cat > "$HOME/Desktop/ENDLUME-UPDATE-SERVER.txt" <<EOF
ENDLUME Cloudflare Update Server
Worker: $WORKER_URL
Bucket: $BUCKET
Public updater key: $PUBLIC_KEY
Private signing key: $KEY (НЕ ПЕРЕДАВАТЬ НИКОМУ)
Runner: $RUNNER_DIR
EOF

echo
echo "✅ ENDLUME Cloudflare infrastructure ready"
echo "✅ R2 bucket приватный"
echo "✅ Worker выдаёт временные download URL на 10 минут"
echo "✅ Tauri private signing key хранится только на этом Mac"
echo "✅ Mac зарегистрирован как self-hosted runner"
echo "✅ Bootstrap сохранён в updates/cloudflare/bootstrap.json"
echo
echo "Теперь напиши в ChatGPT: Cloudflare setup готов."
