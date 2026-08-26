#!/bin/bash
set -Eeuo pipefail

APP_NAME="ENDLUME Studio"
VERSION_EXPECTED="1.0.0-alpha.8.32"
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
WORK_ROOT="$HOME/.endlume-local-builder"
SRC="$WORK_ROOT/endlume-desktop-8.32"
LOG="$HOME/Desktop/ENDLUME-local-build.log"
DEST="/Applications/ENDLUME Studio.app"
STAGE="init"

mkdir -p "$WORK_ROOT"
exec > >(tee "$LOG") 2>&1
stage(){ STAGE="$1"; echo "@@ENDLUME_STAGE|$1"; echo "@@ENDLUME_PROGRESS|$2"; echo; echo "$1"; }
fail(){
  local msg="$1"
  echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "❌ ENDLUME 8.32 остановлена ДО замены приложения"
  echo "Этап: $STAGE"
  echo "$msg"
  echo "Лог: $LOG"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  /usr/bin/osascript -e "display dialog \"ENDLUME Studio не обновлена. Этап: $STAGE. Текущая программа не заменена. Лог: Рабочий стол → ENDLUME-local-build.log\" buttons {\"OK\"} default button \"OK\" with icon stop" >/dev/null 2>&1 || true
  exit 1
}
trap 'fail "Строка $LINENO: $BASH_COMMAND"' ERR
repair_remove(){ local p="$1"; [[ -e "$p" ]] || return 0; /bin/rm -rf "$p" >/dev/null 2>&1 && return 0; sudo /usr/bin/chflags -R nouchg "$p" >/dev/null 2>&1 || true; sudo /usr/bin/chown -R "$(id -un)":staff "$p" >/dev/null 2>&1 || true; sudo /bin/chmod -RN "$p" >/dev/null 2>&1 || true; sudo /bin/chmod -R u+rwX "$p" >/dev/null 2>&1 || true; sudo /bin/rm -rf "$p"; }

clear || true
echo "╭────────────────────────────────────────────────────────────╮"
echo "│                 ENDLUME Studio LOCAL BUILD                 │"
echo "│ 8.32 • queue sync • in-app updater • 8.31 fidelity stack  │"
echo "╰────────────────────────────────────────────────────────────╯"

stage "1/10 Проверяю Mac" 3
[[ "$(uname -s)" == "Darwin" ]] || fail "Нужна macOS."
[[ "$(uname -m)" == "arm64" ]] || fail "Нужен Apple Silicon Mac."
xcode-select -p >/dev/null 2>&1 || { xcode-select --install || true; fail "Установи Command Line Tools и повтори обновление."; }

stage "2/10 Проверяю инструменты" 7
if ! command -v brew >/dev/null 2>&1; then NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; fi
[[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
brew list node@22 >/dev/null 2>&1 || brew install node@22
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
brew list ffmpeg >/dev/null 2>&1 || brew install ffmpeg
brew list gh >/dev/null 2>&1 || brew install gh
if ! command -v cargo >/dev/null 2>&1; then curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal; fi
[[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env"
rustup target add aarch64-apple-darwin >/dev/null
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован. Обновление из приватного release-канала невозможно."

stage "3/10 Получаю чистые исходники" 12
repair_remove "$SRC"
gh repo clone "$REPO" "$SRC" -- --branch "$BRANCH" --single-branch
cd "$SRC"

stage "4/10 Устанавливаю зависимости" 18
npm install --no-audit --no-fund

stage "5/10 Встраиваю FFmpeg и FFprobe" 24
BIN_DIR="$SRC/src-tauri/binaries"; repair_remove "$BIN_DIR"; mkdir -p "$BIN_DIR"
FFMPEG="$BIN_DIR/ffmpeg-aarch64-apple-darwin"; FFPROBE="$BIN_DIR/ffprobe-aarch64-apple-darwin"
/usr/bin/install -m 755 "$(command -v ffmpeg)" "$FFMPEG"
/usr/bin/install -m 755 "$(command -v ffprobe)" "$FFPROBE"
"$FFMPEG" -hide_banner -encoders > /tmp/endlume-832-encoders.txt
"$FFMPEG" -hide_banner -protocols > /tmp/endlume-832-protocols.txt
grep -q libx265 /tmp/endlume-832-encoders.txt || fail "FFmpeg без libx265."
grep -q alac /tmp/endlume-832-encoders.txt || fail "FFmpeg без ALAC."
grep -q concatf /tmp/endlume-832-protocols.txt || fail "FFmpeg без concatf."

stage "6/10 Применяю проверенный стек исправлений" 31
python3 -m py_compile scripts/apply-render-stability-8-25.py scripts/apply-release-ui-8-25.py scripts/apply-smart-repeat-8-26.py scripts/apply-ui-version-8-26.py scripts/apply-original-fidelity-8-27.py scripts/apply-original-fidelity-ui-8-27.py scripts/apply-hybrid-fidelity-8-28.py scripts/apply-hybrid-fidelity-ui-8-28.py scripts/repair-hybrid-patcher-8-29.py scripts/apply-version-8-30.py scripts/apply-runtime-ux-8-31.py scripts/apply-version-8-31.py scripts/apply-queue-updater-8-32.py scripts/apply-version-8-32.py
python3 scripts/repair-hybrid-patcher-8-29.py
python3 -m py_compile scripts/apply-hybrid-fidelity-8-28.py
python3 scripts/apply-render-stability-8-25.py
python3 scripts/apply-release-ui-8-25.py
python3 scripts/apply-smart-repeat-8-26.py
python3 scripts/apply-ui-version-8-26.py
python3 scripts/apply-original-fidelity-8-27.py
python3 scripts/apply-original-fidelity-ui-8-27.py
python3 scripts/apply-hybrid-fidelity-8-28.py
python3 scripts/apply-hybrid-fidelity-ui-8-28.py
python3 scripts/apply-version-8-30.py
python3 scripts/apply-runtime-ux-8-31.py
python3 scripts/apply-version-8-31.py
python3 scripts/apply-queue-updater-8-32.py
python3 scripts/apply-version-8-32.py

stage "6.5/10 Проверяю TypeScript" 40
npm run check
stage "6.6/10 Проверяю production frontend" 45
npm run build
stage "6.7/10 Проверяю Rust" 50
cargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin

stage "7/10 Проверяю очередь, рендер, звук, эффекты и updater" 56
chmod +x scripts/validate-release-8-25.sh scripts/validate-release-8-30.sh scripts/validate-release-8-31.sh scripts/validate-release-8-32.sh
scripts/validate-release-8-25.sh "$FFMPEG" "$FFPROBE"
echo "@@ENDLUME_PROGRESS|62"
scripts/validate-release-8-30.sh "$FFMPEG" "$FFPROBE"
echo "@@ENDLUME_PROGRESS|68"
scripts/validate-release-8-31.sh "$FFMPEG" "$FFPROBE"
echo "@@ENDLUME_PROGRESS|73"
scripts/validate-release-8-32.sh
node scripts/validate-motion-ui.mjs

echo "8/10 Все gates пройдены. Текущая ENDLUME ещё не тронута."
echo "@@ENDLUME_PROGRESS|78"

stage "9/10 Собираю ENDLUME Studio.app" 80
npx tauri build --target aarch64-apple-darwin --bundles app --config src-tauri/tauri.local.conf.json
BUILT_APP="src-tauri/target/aarch64-apple-darwin/release/bundle/macos/ENDLUME Studio.app"
[[ -d "$BUILT_APP" ]] || fail "Tauri не создал .app"
BUNDLE_ID="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$BUILT_APP/Contents/Info.plist")"
BUILT_VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$BUILT_APP/Contents/Info.plist")"
[[ "$BUNDLE_ID" == "studio.endlume.desktop" ]] || fail "Bundle ID: $BUNDLE_ID"
[[ "$BUILT_VERSION" == "$VERSION_EXPECTED" ]] || fail "Версия .app: $BUILT_VERSION"
find "$BUILT_APP/Contents/MacOS" -maxdepth 1 -type f \( -name 'ffmpeg*' -o -name 'ffprobe*' \) -exec /bin/chmod 755 {} +
BUNDLED_FFMPEG="$(find "$BUILT_APP/Contents/MacOS" -maxdepth 1 -type f -name 'ffmpeg*' | head -1)"
BUNDLED_FFPROBE="$(find "$BUILT_APP/Contents/MacOS" -maxdepth 1 -type f -name 'ffprobe*' | head -1)"
[[ -x "$BUNDLED_FFMPEG" && -x "$BUNDLED_FFPROBE" ]] || fail "В .app потерялись FFmpeg/FFprobe."
/usr/bin/codesign --force --deep --sign - "$BUILT_APP" >/dev/null 2>&1
/usr/bin/codesign --verify --deep --strict "$BUILT_APP" >/dev/null 2>&1 || fail "Подпись .app невалидна."

echo "@@ENDLUME_STAGE|9.5/10 Финальная проверка уже собранного приложения"
echo "@@ENDLUME_PROGRESS|91"
SMOKE="$(mktemp -d)"
"$BUNDLED_FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x182038:size=640x360:rate=30' -t 0.6 -an -c:v libx265 -preset ultrafast -crf 22 -tag:v hvc1 -pix_fmt yuv420p -y "$SMOKE/v.mp4"
"$BUNDLED_FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=44100' -t 1 -ac 2 -c:a libmp3lame -b:a 320k -y "$SMOKE/a.mp3"
"$BUNDLED_FFMPEG" -hide_banner -loglevel error -i "$SMOKE/v.mp4" -i "$SMOKE/a.mp3" -map 0:v:0 -map 1:a:0 -c copy -y "$SMOKE/final.mov"
"$BUNDLED_FFMPEG" -hide_banner -loglevel error -i "$SMOKE/final.mov" -map 0:a:0 -t 0.5 -f null -
rm -rf "$SMOKE"

stage "10/10 Устанавливаю обновление" 96
NEW="/Applications/.ENDLUME Studio.new.app"; OLD="/Applications/.ENDLUME Studio.previous.app"
repair_remove "$NEW"; repair_remove "$OLD"
if [[ -w /Applications ]]; then /usr/bin/ditto "$BUILT_APP" "$NEW"; else sudo /usr/bin/ditto "$BUILT_APP" "$NEW"; fi
[[ -d "$NEW" ]] || fail "Не удалось подготовить новую .app"
NEW_VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$NEW/Contents/Info.plist")"
[[ "$NEW_VERSION" == "$VERSION_EXPECTED" ]] || fail "Подготовлена неверная версия: $NEW_VERSION"
osascript -e 'tell application "ENDLUME Studio" to quit' >/dev/null 2>&1 || true; sleep 1; pkill -x "ENDLUME Studio" >/dev/null 2>&1 || true
if [[ -d "$DEST" ]]; then /bin/mv "$DEST" "$OLD"; fi
if /bin/mv "$NEW" "$DEST"; then :; else [[ -d "$OLD" ]] && /bin/mv "$OLD" "$DEST"; fail "Atomic swap не выполнен, старая версия восстановлена."; fi
/usr/bin/xattr -dr com.apple.quarantine "$DEST" >/dev/null 2>&1 || true
FINAL_VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$DEST/Contents/Info.plist")"
if [[ "$FINAL_VERSION" != "$VERSION_EXPECTED" ]]; then repair_remove "$DEST"; [[ -d "$OLD" ]] && /bin/mv "$OLD" "$DEST"; fail "Финальная версия неверная; rollback выполнен."; fi
open "$DEST"
sleep 2
repair_remove "$OLD"
rm -rf "$HOME/Library/Caches/studio.endlume.desktop/render-work" >/dev/null 2>&1 || true

echo "@@ENDLUME_STAGE|Готово — ENDLUME $VERSION_EXPECTED установлена"
echo "@@ENDLUME_PROGRESS|100"
echo "✅ Вторая и последующие задачи видны в Рендере"
echo "✅ Обновления дальше запускаются внутри ENDLUME без Terminal"
echo "✅ GitHub Actions не используются"
