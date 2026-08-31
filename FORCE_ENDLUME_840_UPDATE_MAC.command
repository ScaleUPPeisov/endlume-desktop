#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
EXPECTED="1.0.0-alpha.8.40"
ROOT="$HOME/.endlume-force-840"
CHECKOUT="$ROOT/repo"
LOG="$HOME/Desktop/ENDLUME-8.40-FORCE-UPDATE.log"
KEY="$HOME/.endlume-updater/endlume.key"
PUB="$KEY.pub"
PLIST="$HOME/Library/LaunchAgents/studio.endlume.github-release-agent.plist"
AGENT_LABEL="studio.endlume.github-release-agent"
PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME COPYFILE_DISABLE=1 COPY_EXTENDED_ATTRIBUTES_DISABLE=1
mkdir -p "$ROOT"
exec > >(tee "$LOG") 2>&1
fail(){ echo; echo "❌ ENDLUME 8.40 FORCE: $1"; echo "Лог: $LOG"; exit 1; }
restart_agent(){
  if [[ -f "$PLIST" ]]; then
    launchctl bootstrap "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
    launchctl kickstart -k "gui/$(id -u)/$AGENT_LABEL" >/dev/null 2>&1 || true
  fi
}
trap restart_agent EXIT

echo "ENDLUME Studio • 8.40 • УСТАНОВИТЬ СЕЙЧАС"
echo "Без VPS / JustHost / Cloudflare / GitHub Actions"
echo
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"
[[ -s "$KEY" && -s "$PUB" ]] || fail "ключ подписи updater не найден; сначала запусти SIMPLE UPDATER setup"

# Stop the polling agent during the foreground build to avoid duplicate builds.
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
rm -rf "$HOME/.endlume-github-release-agent/lock" >/dev/null 2>&1 || true

echo "1/4 Получаю актуальный ENDLUME release…"
if [[ ! -d "$CHECKOUT/.git" ]]; then
  rm -rf "$CHECKOUT"
  gh repo clone "$REPO" "$CHECKOUT" -- --branch "$BRANCH" --single-branch || fail "не удалось клонировать приватный репозиторий"
else
  git -C "$CHECKOUT" fetch origin "$BRANCH" --quiet || fail "git fetch failed"
  git -C "$CHECKOUT" reset --hard "origin/$BRANCH" --quiet || fail "git reset failed"
  git -C "$CHECKOUT" clean -fd --quiet || fail "git clean failed"
fi
cd "$CHECKOUT"

python3 - <<'PY'
import json
r=json.load(open('updates/github/build-request.json'))
assert r.get('enabled') is True, 'build-request disabled'
assert r.get('version')=='1.0.0-alpha.8.40', r.get('version')
assert r.get('builder')=='BUILD_ENDLUME_840_GITHUB.command', r.get('builder')
print('✅ build-request 8.40 активен')
PY
/bin/bash -n BUILD_ENDLUME_840_GITHUB.command || fail "8.40 builder syntax error"
/bin/bash -n scripts/publish-github-release-macos.sh || fail "publisher syntax error"

echo "2/4 Собираю и подписываю 8.40…"
echo "Это самый долгий этап. Окно Terminal не закрывай."
/bin/bash scripts/publish-github-release-macos.sh || fail "сборка/публикация 8.40 завершилась ошибкой"

echo "3/4 Проверяю опубликованный update channel…"
ASSETS="$(gh api repos/ScaleUPPeisov/scaleup-site/releases/tags/endlume-stable --jq '[.assets[].name]|join(" ")')"
[[ "$ASSETS" == *"latest.json"* ]] || fail "latest.json не опубликован"
[[ "$ASSETS" == *"ENDLUME-macos-aarch64.app.tar.gz"* ]] || fail "macOS updater artifact не опубликован"
[[ "$ASSETS" == *"ENDLUME-macos-aarch64.app.tar.gz.sig"* ]] || fail "подпись updater artifact не опубликована"

echo "4/4 Проверяю установленную ENDLUME…"
DEST="/Applications/ENDLUME Studio.app"
[[ -f "$DEST/Contents/Info.plist" ]] || fail "ENDLUME Studio.app не найдена в /Applications"
VER="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$DEST/Contents/Info.plist" 2>/dev/null || true)"
[[ "$VER" == "$EXPECTED" ]] || fail "на Mac установлена версия $VER вместо $EXPECTED"
/usr/bin/codesign --verify --deep --strict "$DEST" >/dev/null 2>&1 || fail "подпись установленной .app невалидна"

restart_agent
trap - EXIT

echo
echo "✅ ENDLUME 8.40 УСТАНОВЛЕНА НА MAC"
echo "✅ Native signed updater подключён"
echo "✅ Следующее обновление 8.41 будет ставиться внутри ENDLUME"
echo "✅ Terminal для обычных будущих обновлений больше не нужен"
/usr/bin/open "$DEST" >/dev/null 2>&1 || true
