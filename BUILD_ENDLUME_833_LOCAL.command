#!/bin/bash
set -Eeuo pipefail

APP_NAME="ENDLUME Studio"
VERSION_EXPECTED="1.0.0-alpha.8.33"
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
LOG="$HOME/Desktop/ENDLUME-local-build.log"
DEST="/Applications/ENDLUME Studio.app"
STAGE="init"

stage(){ STAGE="$1"; echo "@@ENDLUME_STAGE|$1"; echo "@@ENDLUME_PROGRESS|$2"; echo; echo "$1"; }
fail(){
  local msg="$1"
  echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "❌ ENDLUME 8.33 остановлена ДО замены приложения"
  echo "Этап: $STAGE"
  echo "$msg"
  echo "Лог: $LOG"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  if [[ "${ENDLUME_IN_APP_UPDATE:-0}" != "1" ]]; then
    /usr/bin/osascript -e "display dialog \"ENDLUME Studio не обновлена. Этап: $STAGE. Текущая программа не заменена. Лог: Рабочий стол → ENDLUME-local-build.log\" buttons {\"OK\"} default button \"OK\" with icon stop" >/dev/null 2>&1 || true
  fi
  exit 1
}
trap 'fail "Строка $LINENO: $BASH_COMMAND"' ERR
repair_remove(){ local p="$1"; [[ -e "$p" ]] || return 0; /bin/rm -rf "$p" >/dev/null 2>&1 && return 0; sudo /usr/bin/chflags -R nouchg "$p" >/dev/null 2>&1 || true; sudo /usr/bin/chown -R "$(id -un)":staff "$p" >/dev/null 2>&1 || true; sudo /bin/chmod -RN "$p" >/dev/null 2>&1 || true; sudo /bin/chmod -R u+rwX "$p" >/dev/null 2>&1 || true; sudo /bin/rm -rf "$p"; }

# Prefer the writable external volume with the most free space. This keeps the
# multi-GB Rust/Tauri build away from a nearly-full internal Mac SSD.
choose_work_root(){
  local best="" best_kb=0 v kb
  for v in /Volumes/*; do
    [[ -d "$v" && -w "$v" ]] || continue
    [[ "$v" == "/Volumes/Macintosh HD" ]] && continue
    kb="$(/bin/df -Pk "$v" 2>/dev/null | /usr/bin/awk 'NR==2{print $4}' || echo 0)"
    [[ "$kb" =~ ^[0-9]+$ ]] || kb=0
    if (( kb > best_kb && kb > 15728640 )); then best="$v"; best_kb="$kb"; fi
  done
  if [[ -n "$best" ]]; then echo "$best/.ENDLUME-build"; else echo "$HOME/.endlume-local-builder"; fi
}
WORK_ROOT="$(choose_work_root)"
SRC="$WORK_ROOT/endlume-desktop-8.33"
mkdir -p "$WORK_ROOT"
exec > >(tee "$LOG") 2>&1

clear >/dev/null 2>&1 || true
echo "╭────────────────────────────────────────────────────────────╮"
echo "│                 ENDLUME Studio LOCAL BUILD                 │"
echo "│ 8.33 • SSD workdir • Fast Fidelity • Preview repair       │"
echo "╰────────────────────────────────────────────────────────────╯"
echo "Build workspace: $WORK_ROOT"

stage "1/10 Проверяю Mac и освобождаю старый cache" 3
[[ "$(uname -s)" == "Darwin" ]] || fail "Нужна macOS."
[[ "$(uname -m)" == "arm64" ]] || fail "Нужен Apple Silicon Mac."
xcode-select -p >/dev/null 2>&1 || { xcode-select --install || true; fail "Установи Command Line Tools и повтори обновление."; }
# Safe-to-delete generated data only. User projects/results are never touched.
/bin/rm -rf "$HOME/Library/Caches/studio.endlume.desktop/effects-v4-aspect-safe" >/dev/null 2>&1 || true
/bin/rm -rf "$HOME/Library/Caches/studio.endlume.desktop/render-work" >/dev/null 2>&1 || true
if [[ "$WORK_ROOT" != "$HOME/.endlume-local-builder" ]]; then
  /bin/rm -rf "$HOME/.endlume-local-builder"/endlume-desktop-* >/dev/null 2>&1 || true
fi

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
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован. Приватный release-канал недоступен."

stage "3/10 Получаю чистые исходники" 12
repair_remove "$SRC"
gh repo clone "$REPO" "$SRC" -- --branch "$BRANCH" --single-branch
cd "$SRC"

stage "4/10 Устанавливаю frontend-зависимости" 18
npm install --no-audit --no-fund

stage "5/10 Встраиваю FFmpeg и FFprobe" 24
BIN_DIR="$SRC/src-tauri/binaries"; repair_remove "$BIN_DIR"; mkdir -p "$BIN_DIR"
FFMPEG="$BIN_DIR/ffmpeg-aarch64-apple-darwin"; FFPROBE="$BIN_DIR/ffprobe-aarch64-apple-darwin"
/usr/bin/install -m 755 "$(command -v ffmpeg)" "$FFMPEG"
/usr/bin/install -m 755 "$(command -v ffprobe)" "$FFPROBE"
"$FFMPEG" -hide_banner -encoders > /tmp/endlume-833-encoders.txt
"$FFMPEG" -hide_banner -protocols > /tmp/endlume-833-protocols.txt
grep -q libx265 /tmp/endlume-833-encoders.txt || fail "FFmpeg без libx265 fallback."
grep -q hevc_videotoolbox /tmp/endlume-833-encoders.txt || fail "FFmpeg без Apple HEVC VideoToolbox."
grep -q alac /tmp/endlume-833-encoders.txt || fail "FFmpeg без ALAC."
grep -q concatf /tmp/endlume-833-protocols.txt || fail "FFmpeg без concatf."

stage "6/10 Применяю проверенный стек исправлений" 31
python3 -m py_compile \
  scripts/apply-render-stability-8-25.py scripts/apply-release-ui-8-25.py \
  scripts/apply-smart-repeat-8-26.py scripts/apply-ui-version-8-26.py \
  scripts/apply-original-fidelity-8-27.py scripts/apply-original-fidelity-ui-8-27.py \
  scripts/apply-hybrid-fidelity-8-28.py scripts/apply-hybrid-fidelity-ui-8-28.py \
  scripts/repair-hybrid-patcher-8-29.py scripts/apply-version-8-30.py \
  scripts/apply-runtime-ux-8-31.py scripts/apply-version-8-31.py \
  scripts/apply-queue-updater-8-32.py scripts/apply-version-8-32.py \
  scripts/apply-speed-fidelity-8-33.py scripts/apply-version-8-33.py
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
chmod +x scripts/validate-release-8-32.sh
scripts/validate-release-8-32.sh
python3 scripts/apply-speed-fidelity-8-33.py
python3 scripts/apply-version-8-33.py

stage "6.5/10 Проверяю TypeScript" 40
npm run check
stage "6.6/10 Проверяю production frontend и все button handlers" 45
npm run build
# Critical controls must remain connected after the targeted patch.
grep -Fq 'onClick={enqueue}' src/pages/ProjectPage.tsx || fail "Кнопка ДОБАВИТЬ В ОЧЕРЕДЬ потеряла handler."
grep -Fq "openEditor({kind:'subscribe'})" src/pages/ProjectPage.tsx || fail "Кнопка Subscribe потеряла handler."
grep -Fq "openEditor({kind:'effects'})" src/pages/ProjectPage.tsx || fail "Кнопка Effects потеряла handler."
grep -Fq 'onClick={pick}' src/pages/ProjectPage.tsx || fail "Выбор проекта потерял handler."

stage "6.7/10 Проверяю Rust" 50
cargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin

stage "7/10 Гоняю Effects / Subscribe / Audio / SSD / Fast Fidelity regression" 58
chmod +x scripts/validate-release-8-33.sh
scripts/validate-release-8-33.sh "$FFMPEG" "$FFPROBE"
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

echo "@@ENDLUME_STAGE|9.5/10 Финальный smoke уже собранного приложения"
echo "@@ENDLUME_PROGRESS|91"
SMOKE="$(mktemp -d)"
"$BUNDLED_FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x182038:size=1920x1080:rate=30' -t 1 -an -c:v hevc_videotoolbox -realtime 1 -b:v 600k -tag:v hvc1 -pix_fmt yuv420p -y "$SMOKE/v.mp4"
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
# Remove only generated caches/builds after successful install.
/bin/rm -rf "$HOME/Library/Caches/studio.endlume.desktop/effects-v4-aspect-safe" >/dev/null 2>&1 || true
/bin/rm -rf "$HOME/.endlume-local-builder"/endlume-desktop-* >/dev/null 2>&1 || true
cd /
repair_remove "$SRC" >/dev/null 2>&1 || true

echo "@@ENDLUME_STAGE|Готово — ENDLUME $VERSION_EXPECTED установлена"
echo "@@ENDLUME_PROGRESS|100"
echo "✅ AppleDouble ._* больше не ломает Effects/Subscribe Preview"
echo "✅ Render work идёт на выбранный диск результата (TOSHIBA SSD, если он выбран)"
echo "✅ Smart Fidelity: Apple HEVC hardware first, x265 quality fallback"
echo "✅ Noise 1/2 удалены"
echo "✅ MP3 bitstream-copy и lossless crossfade сохранены"
echo "✅ GitHub Actions не используются"