#!/bin/bash
set -Eeuo pipefail

APP_NAME="ENDLUME Studio"
VERSION_EXPECTED="1.0.0-alpha.8.30"
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
WORK_ROOT="$HOME/.endlume-local-builder"
SRC="$WORK_ROOT/endlume-desktop-8.30"
LOG="$HOME/Desktop/ENDLUME-local-build.log"
DEST="/Applications/ENDLUME Studio.app"
STAGE="init"

mkdir -p "$WORK_ROOT"
exec > >(tee "$LOG") 2>&1
fail(){
  local msg="$1"
  echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "❌ ENDLUME 8.30 остановлена ДО замены приложения"
  echo "Этап: $STAGE"
  echo "$msg"
  echo "Лог: $LOG"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  /usr/bin/osascript -e "display dialog \"ENDLUME Studio не установлена. Этап: $STAGE. Текущая программа не заменена. Подробности: Рабочий стол → ENDLUME-local-build.log\" buttons {\"OK\"} default button \"OK\" with icon stop" >/dev/null 2>&1 || true
  exit 1
}
trap 'fail "Строка $LINENO: $BASH_COMMAND"' ERR
repair_remove(){ local p="$1"; [[ -e "$p" ]] || return 0; /bin/rm -rf "$p" >/dev/null 2>&1 && return 0; sudo /usr/bin/chflags -R nouchg "$p" >/dev/null 2>&1 || true; sudo /usr/bin/chown -R "$(id -un)":staff "$p" >/dev/null 2>&1 || true; sudo /bin/chmod -RN "$p" >/dev/null 2>&1 || true; sudo /bin/chmod -R u+rwX "$p" >/dev/null 2>&1 || true; sudo /bin/rm -rf "$p"; }

clear
echo "╭──────────────────────────────────────────────────────────╮"
echo "│                ENDLUME Studio LOCAL BUILD                │"
echo "│ 8.30 • fresh clone • ~1GB/2h • exact MP3 • 4K fidelity │"
echo "╰──────────────────────────────────────────────────────────╯"

STAGE="1/10 Mac"
[[ "$(uname -s)" == "Darwin" ]] || fail "Нужна macOS."
[[ "$(uname -m)" == "arm64" ]] || fail "Нужен Apple Silicon Mac."
xcode-select -p >/dev/null 2>&1 || { xcode-select --install || true; fail "Установи Command Line Tools и запусти ещё раз."; }

STAGE="2/10 tools"
if ! command -v brew >/dev/null 2>&1; then NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; fi
[[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
brew list node@22 >/dev/null 2>&1 || brew install node@22
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
brew list ffmpeg >/dev/null 2>&1 || brew install ffmpeg
brew list gh >/dev/null 2>&1 || brew install gh
if ! command -v cargo >/dev/null 2>&1; then curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal; fi
[[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env"
rustup target add aarch64-apple-darwin >/dev/null
if ! gh auth status -h github.com >/dev/null 2>&1; then gh auth login -h github.com -p https -w; fi

STAGE="3/10 fresh source"
repair_remove "$SRC"
gh repo clone "$REPO" "$SRC" -- --branch "$BRANCH" --single-branch
cd "$SRC"
VERSION="$(node -p "require('./package.json').version")"
[[ "$VERSION" == "$VERSION_EXPECTED" ]] || fail "Ожидалась $VERSION_EXPECTED, получена $VERSION"

STAGE="4/10 frontend dependencies"
npm install --no-audit --no-fund

STAGE="5/10 bundled FFmpeg"
BIN_DIR="$SRC/src-tauri/binaries"; repair_remove "$BIN_DIR"; mkdir -p "$BIN_DIR"
FFMPEG="$BIN_DIR/ffmpeg-aarch64-apple-darwin"; FFPROBE="$BIN_DIR/ffprobe-aarch64-apple-darwin"
/usr/bin/install -m 755 "$(command -v ffmpeg)" "$FFMPEG"
/usr/bin/install -m 755 "$(command -v ffprobe)" "$FFPROBE"
"$FFMPEG" -hide_banner -encoders > /tmp/endlume-830-encoders.txt
"$FFMPEG" -hide_banner -protocols > /tmp/endlume-830-protocols.txt
grep -q libx265 /tmp/endlume-830-encoders.txt || fail "FFmpeg без libx265."
grep -q alac /tmp/endlume-830-encoders.txt || fail "FFmpeg без ALAC fallback."
grep -q concatf /tmp/endlume-830-protocols.txt || fail "FFmpeg без concatf."

STAGE="6/10 patch preflight"
python3 -m py_compile scripts/apply-render-stability-8-25.py scripts/apply-release-ui-8-25.py scripts/apply-smart-repeat-8-26.py scripts/apply-ui-version-8-26.py scripts/apply-original-fidelity-8-27.py scripts/apply-original-fidelity-ui-8-27.py scripts/apply-hybrid-fidelity-8-28.py scripts/apply-hybrid-fidelity-ui-8-28.py scripts/repair-hybrid-patcher-8-29.py scripts/apply-version-8-30.py
python3 scripts/repair-hybrid-patcher-8-29.py
python3 -m py_compile scripts/apply-hybrid-fidelity-8-28.py

STAGE="6.1/10 apply render stack"
python3 scripts/apply-render-stability-8-25.py
python3 scripts/apply-release-ui-8-25.py
python3 scripts/apply-smart-repeat-8-26.py
python3 scripts/apply-ui-version-8-26.py
python3 scripts/apply-original-fidelity-8-27.py
python3 scripts/apply-original-fidelity-ui-8-27.py
python3 scripts/apply-hybrid-fidelity-8-28.py
python3 scripts/apply-hybrid-fidelity-ui-8-28.py
python3 scripts/apply-version-8-30.py

grep -Fq 'fn render_work_dir(' src-tauri/src/render.rs || fail "Render recovery отсутствует."
grep -Fq 'fn hybrid_fidelity_args(' src-tauri/src/render.rs || fail "Hybrid Fidelity отсутствует."
grep -Fq '"-crf","22"' src-tauri/src/render.rs || fail "CRF22 fidelity profile отсутствует."
grep -Fq 'audio-original-clean.mp3' src-tauri/src/render.rs || fail "Exact MP3 path отсутствует."
grep -Fq 'probe_audio_decodes(app,out)' src-tauri/src/render.rs || fail "Проверка реального звука отсутствует."
grep -Fq "chooseVideo('subscribe')" src/pages/Editors.tsx || fail "Subscribe import regression."
grep -Fq 'version = "1.0.0-alpha.8.30"' src-tauri/Cargo.toml || fail "Rust version не 8.30."
grep -Fq '"version": "1.0.0-alpha.8.30"' src-tauri/tauri.conf.json || fail "Tauri version не 8.30."
grep -Fq '"build": "tsc && vite build"' package.json || fail "Build не должен мутировать исходники."

STAGE="6.5/10 TypeScript"
npm run check
STAGE="6.6/10 production frontend"
npm run build
STAGE="6.7/10 Rust"
cargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin

STAGE="7/10 Render Effects Subscribe exact-MP3 4K"
chmod +x scripts/validate-release-8-25.sh scripts/validate-release-8-29.sh scripts/validate-release-8-30.sh
scripts/validate-release-8-25.sh "$FFMPEG" "$FFPROBE"
scripts/validate-release-8-30.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs

echo "8/10 Все preflight/runtime gates пройдены. Текущая ENDLUME всё ещё не тронута."

STAGE="9/10 Tauri app build"
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

STAGE="9.5/10 built-app smoke"
SMOKE="$(mktemp -d)"
"$BUNDLED_FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x182038:size=640x360:rate=30' -t 1 -an -c:v libx265 -preset ultrafast -crf 22 -tag:v hvc1 -pix_fmt yuv420p -y "$SMOKE/v.mp4"
"$BUNDLED_FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=44100' -t 1 -ac 2 -c:a libmp3lame -b:a 320k -y "$SMOKE/a.mp3"
"$BUNDLED_FFMPEG" -hide_banner -loglevel error -i "$SMOKE/v.mp4" -i "$SMOKE/a.mp3" -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy -movflags +faststart -y "$SMOKE/final.mov"
"$BUNDLED_FFMPEG" -hide_banner -loglevel error -i "$SMOKE/final.mov" -map 0:a:0 -t .5 -f null -
[[ "$("$BUNDLED_FFPROBE" -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$SMOKE/final.mov")" == "mp3" ]] || fail "Собранная .app не сохраняет MP3."
rm -rf "$SMOKE"

STAGE="10/10 atomic install"
NEW="/Applications/.ENDLUME Studio.new.app"; OLD="/Applications/.ENDLUME Studio.previous.app"
repair_remove "$NEW"; repair_remove "$OLD"
if [[ -w /Applications ]]; then /usr/bin/ditto "$BUILT_APP" "$NEW"; else sudo /usr/bin/ditto "$BUILT_APP" "$NEW"; fi
[[ -d "$NEW" ]] || fail "Не удалось подготовить новую .app в /Applications."
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

echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ENDLUME Studio $VERSION_EXPECTED установлена"
echo "✅ Fresh clone: без старого source-cache"
echo "✅ 4K representative fidelity gate: SSIM >= 0.995"
echo "✅ Typical 1-image + sparse overlays: цель около 1 ГБ / 2 ч"
echo "✅ Compatible MP3: bitstream-copy без повторного lossy-кодирования"
echo "✅ Effects/Subscribe: runtime gates пройдены"
echo "✅ Atomic install + rollback + одна ENDLUME Studio.app"
echo "✅ GitHub Actions не запускались"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
