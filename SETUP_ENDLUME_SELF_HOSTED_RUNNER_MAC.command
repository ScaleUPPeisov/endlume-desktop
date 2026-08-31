#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
RUNNER_ROOT="$HOME/.github-runners/endlume-desktop-macos-arm64"
RUNNER_NAME="kirill-mac-endlume"
LABELS="endlume,macos-arm64"
OLD_PLIST="$HOME/Library/LaunchAgents/studio.endlume.github-release-agent.plist"
LOG_DIR="$HOME/.endlume-updater"
LOG="$LOG_DIR/SELF-HOSTED-RUNNER-SETUP.log"
TMP="$(mktemp -d /tmp/endlume-self-hosted.XXXXXX)"

cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
mkdir -p "$LOG_DIR"
exec > >(tee "$LOG") 2>&1

fail(){
  echo
  echo "❌ ENDLUME SELF-HOSTED: $1"
  echo "Лог: $LOG"
  exit 1
}

export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME

echo "ENDLUME • GITHUB SELF-HOSTED RUNNER"
echo "Mac M1/M2/M3/M4 • без GitHub-hosted minutes • без карты"
echo

[[ "$(uname -s)" == "Darwin" ]] || fail "нужна macOS"
[[ "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

# Stop the old custom release-agent so only GitHub Actions controls production builds.
UID_NOW="$(id -u)"
if [[ -f "$OLD_PLIST" ]]; then
  launchctl bootout "gui/$UID_NOW" "$OLD_PLIST" >/dev/null 2>&1 || true
  /bin/mv "$OLD_PLIST" "$OLD_PLIST.disabled" >/dev/null 2>&1 || true
fi
/bin/rm -rf "$HOME/.endlume-github-release-agent/lock" >/dev/null 2>&1 || true

echo "1/5 Получаю официальный GitHub Actions Runner…"
TAG="$(gh api repos/actions/runner/releases/latest --jq .tag_name)"
[[ "$TAG" == v* ]] || fail "не удалось определить версию runner"
VER="${TAG#v}"
ARCHIVE="actions-runner-osx-arm64-${VER}.tar.gz"
URL="https://github.com/actions/runner/releases/download/${TAG}/${ARCHIVE}"
echo "Runner: $TAG"
/usr/bin/curl -fL --retry 3 --connect-timeout 15 --max-time 300 "$URL" -o "$TMP/$ARCHIVE" || fail "runner download failed"
/usr/bin/tar -tzf "$TMP/$ARCHIVE" >/dev/null || fail "runner archive damaged"

# Clean an older ENDLUME runner registration/service if this setup is re-run.
if [[ -d "$RUNNER_ROOT" ]]; then
  if [[ -x "$RUNNER_ROOT/svc.sh" ]]; then
    (cd "$RUNNER_ROOT" && ./svc.sh stop >/dev/null 2>&1 || true)
    (cd "$RUNNER_ROOT" && ./svc.sh uninstall >/dev/null 2>&1 || true)
  fi
  if [[ -x "$RUNNER_ROOT/config.sh" && -f "$RUNNER_ROOT/.runner" ]]; then
    REMOVE_TOKEN="$(gh api --method POST "/repos/$REPO/actions/runners/remove-token" --jq .token 2>/dev/null || true)"
    if [[ -n "$REMOVE_TOKEN" ]]; then
      (cd "$RUNNER_ROOT" && ./config.sh remove --unattended --token "$REMOVE_TOKEN" >/dev/null 2>&1 || true)
    fi
  fi
  /bin/rm -rf "$RUNNER_ROOT"
fi
mkdir -p "$RUNNER_ROOT"
/usr/bin/tar -xzf "$TMP/$ARCHIVE" -C "$RUNNER_ROOT"
[[ -x "$RUNNER_ROOT/config.sh" ]] || fail "config.sh missing"

echo "2/5 Регистрирую runner только для ENDLUME…"
REG_TOKEN="$(gh api --method POST "/repos/$REPO/actions/runners/registration-token" --jq .token)"
[[ -n "$REG_TOKEN" ]] || fail "registration token empty"
(
  cd "$RUNNER_ROOT"
  ./config.sh \
    --unattended \
    --replace \
    --url "https://github.com/$REPO" \
    --token "$REG_TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "$LABELS" \
    --work _work
) || fail "runner configuration failed"
unset REG_TOKEN

echo "3/5 Устанавливаю runner как фоновый сервис…"
(
  cd "$RUNNER_ROOT"
  ./svc.sh install
  ./svc.sh start
) || fail "runner service install/start failed"

sleep 3
(
  cd "$RUNNER_ROOT"
  ./svc.sh status || true
)

ONLINE="$(gh api "/repos/$REPO/actions/runners" --jq '.runners[] | select(.name=="'"$RUNNER_NAME"'") | .status' 2>/dev/null | head -1 || true)"
[[ "$ONLINE" == "online" || "$ONLINE" == "busy" ]] || fail "GitHub пока не видит runner online (status=$ONLINE)"
echo "✅ GitHub видит runner: $ONLINE"

echo "4/5 Запускаю первую self-hosted сборку…"
REQ="$TMP/build-request.json"
META="$TMP/build-request-meta.json"
gh api "/repos/$REPO/contents/updates/github/build-request.json?ref=$BRANCH" > "$META" || fail "build-request metadata unavailable"
python3 - "$META" "$REQ" <<'PY'
import json,sys,base64
m=json.load(open(sys.argv[1]))
raw=base64.b64decode(m['content']).decode()
r=json.loads(raw)
r['enabled']=True
r['generation']=int(r.get('generation',0))+1
json.dump(r,open(sys.argv[2],'w'),ensure_ascii=False,indent=2)
print('Next generation:',r['generation'])
PY
SHA="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["sha"])' "$META")"
python3 - "$REQ" "$TMP/payload.json" "$SHA" "$BRANCH" <<'PY'
import json,sys,base64,pathlib
src,out,sha,branch=sys.argv[1:]
p={
  'message':'ENDLUME: start self-hosted release generation',
  'branch':branch,
  'sha':sha,
  'content':base64.b64encode(pathlib.Path(src).read_bytes()).decode()
}
json.dump(p,open(out,'w'))
PY
gh api --method PUT "/repos/$REPO/contents/updates/github/build-request.json" --input "$TMP/payload.json" >/dev/null || fail "cannot trigger self-hosted release"

echo "5/5 Проверяю, что workflow создан…"
gh api "/repos/$REPO/contents/.github/workflows/endlume-self-hosted-release.yml?ref=$BRANCH" --jq .sha >/dev/null || fail "self-hosted workflow missing"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ENDLUME SELF-HOSTED RUNNER READY"
echo "✅ Runner: $RUNNER_NAME"
echo "✅ Labels: self-hosted / macOS / ARM64 / $LABELS"
echo "✅ GitHub-hosted minutes: НЕ ИСПОЛЬЗУЮТСЯ"
echo "✅ Банковская карта: НЕ НУЖНА"
echo "✅ Первая ENDLUME release-сборка уже отправлена runner'у"
echo "✅ Старый custom release-agent отключён"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "Дальше Mac просто должен быть включён и иметь интернет."
echo "Новые ENDLUME releases будут запускаться изменением build-request.json."
