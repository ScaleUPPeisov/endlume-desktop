#!/bin/bash
set -Eeuo pipefail

APP_NAME="ENDLUME Studio"
VERSION_EXPECTED="1.0.0-alpha.8.27"
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
WORK_ROOT="$HOME/.endlume-local-builder"
SRC="$WORK_ROOT/endlume-desktop"
LOG="$HOME/Desktop/ENDLUME-local-build.log"
DEST="/Applications/ENDLUME Studio.app"

mkdir -p "$WORK_ROOT"
exec > >(tee "$LOG") 2>&1

fail(){
  echo
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "❌ ENDLUME local build остановлен"
  echo "$1"
  echo "Лог: $LOG"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  osascript -e 'display dialog "ENDLUME Studio не собрана. Лог сохранён на Рабочем столе: ENDLUME-local-build.log" buttons {"OK"} default button "OK" with icon stop' >/dev/null 2>&1 || true
  exit 1
}
trap 'fail "Ошибка на строке $LINENO. Команда: $BASH_COMMAND"' ERR

repair_and_remove(){
  local p="$1"
  [[ -e "$p" ]] || return 0
  /bin/rm -rf "$p" >/dev/null 2>&1 && return 0
  sudo /usr/bin/chflags -R nouchg "$p" >/dev/null 2>&1 || true
  sudo /usr/bin/chown -R "$(id -un)":staff "$p" >/dev/null 2>&1 || true
  sudo /bin/chmod -RN "$p" >/dev/null 2>&1 || true
  sudo /bin/chmod -R u+rwX "$p" >/dev/null 2>&1 || true
  sudo /bin/rm -rf "$p" || fail "Не удалось очистить старый build-кэш: $p"
}

clear
echo "╭────────────────────────────────────────────────────────╮"
echo "│               ENDLUME Studio LOCAL BUILD               │"
echo "│ Original Fidelity • Exact MP3 • HEVC Quality • M1+    │"
echo "╰────────────────────────────────────────────────────────╯"
echo

echo "1/10  Проверяю Mac…"
[[ "$(uname -s)" == "Darwin" ]] || fail "Builder предназначен для macOS."
[[ "$(uname -m)" == "arm64" ]] || fail "Нужен Apple Silicon Mac."
if ! xcode-select -p >/dev/null 2>&1; then xcode-select --install || true; fail "После установки Command Line Tools запусти builder снова."; fi

echo "2/10  Проверяю Homebrew / Node / Rust / FFmpeg…"
if ! command -v brew >/dev/null 2>&1; then NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; fi
[[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
brew list node@22 >/dev/null 2>&1 || brew install node@22
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
brew list ffmpeg >/dev/null 2>&1 || brew install ffmpeg
brew list gh >/dev/null 2>&1 || brew install gh
if ! command -v cargo >/dev/null 2>&1; then curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal; fi
[[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env"
rustup target add aarch64-apple-darwin >/dev/null

if ! gh auth status -h github.com >/dev/null 2>&1; then echo "Авторизуй GitHub в браузере. Actions НЕ запускаются."; gh auth login -h github.com -p https -w; fi

echo "3/10  Получаю чистую release-ветку…"
if [[ -d "$SRC/.git" ]]; then
  git -C "$SRC" fetch origin "$BRANCH"
  git -C "$SRC" checkout "$BRANCH"
  git -C "$SRC" reset --hard "origin/$BRANCH"
  git -C "$SRC" clean -fd
else
  rm -rf "$SRC"
  gh repo clone "$REPO" "$SRC" -- --branch "$BRANCH" --single-branch
fi
cd "$SRC"
repair_and_remove "$SRC/src-tauri/binaries"
VERSION="$(node -p "require('./package.json').version")"
[[ "$VERSION" == "$VERSION_EXPECTED" ]] || fail "Ожидалась $VERSION_EXPECTED, получена $VERSION"

echo "4/10  Устанавливаю frontend-зависимости…"
npm install --no-audit --no-fund

echo "5/10  Встраиваю FFmpeg/FFprobe…"
BIN_DIR="$SRC/src-tauri/binaries"
FFMPEG="$BIN_DIR/ffmpeg-aarch64-apple-darwin"
FFPROBE="$BIN_DIR/ffprobe-aarch64-apple-darwin"
mkdir -p "$BIN_DIR"
/usr/bin/install -m 755 "$(command -v ffmpeg)" "$FFMPEG"
/usr/bin/install -m 755 "$(command -v ffprobe)" "$FFPROBE"
[[ -x "$FFMPEG" && -x "$FFPROBE" ]] || fail "FFmpeg/FFprobe не встроились."
"$FFMPEG" -hide_banner -encoders > /tmp/endlume-827-encoders.txt
grep -q 'hevc_videotoolbox' /tmp/endlume-827-encoders.txt || fail "Нет HEVC VideoToolbox — Original Fidelity не может использовать быстрый Mac encoder."
grep -q 'libx265' /tmp/endlume-827-encoders.txt || fail "Нет libx265 fidelity fallback."
grep -q 'alac' /tmp/endlume-827-encoders.txt || fail "Нет ALAC lossless audio fallback."

echo "6/10  Применяю Render Stability + Smart Repeat + Original Fidelity 8.27…"
python3 scripts/apply-render-stability-8-25.py
python3 scripts/apply-release-ui-8-25.py
python3 scripts/apply-smart-repeat-8-26.py
python3 scripts/apply-ui-version-8-26.py
python3 scripts/apply-original-fidelity-8-27.py
python3 scripts/apply-original-fidelity-ui-8-27.py

grep -Fq 'fn render_work_dir(' src-tauri/src/render.rs || fail "Render workspace fix не применился."
grep -Fq 'fn smart_repeat_project(' src-tauri/src/render.rs || fail "Smart Repeat detector отсутствует."
grep -Fq 'fn fidelity_video_args(' src-tauri/src/render.rs || fail "Original Fidelity video path отсутствует."
grep -Fq 'build_original_audio_cycle(' src-tauri/src/render.rs || fail "Original MP3 stream-copy path отсутствует."
grep -Fq '"-c:a","alac"' src-tauri/src/render.rs || fail "ALAC lossless fallback отсутствует."
grep -Fq 'choose_fidelity_encoder(app,attempt).await' src-tauri/src/render.rs || fail "HEVC fidelity selector отсутствует."
grep -Fq "chooseVideo('subscribe')" src/pages/Editors.tsx || fail "Subscribe managed-import fix отсутствует."
grep -Fq '1.0.0-alpha.8.27' src/tauri.ts || fail "Frontend current-version не синхронизирован."
grep -Fq '"build": "tsc && vite build"' package.json || fail "Build снова мутирует исходники."

echo "6.5/10 Проверяю TypeScript…"
npm run check

echo "6.6/10 Проверяю production frontend…"
npm run build

echo "6.7/10 Проверяю Rust…"
cargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin

echo "7/10  Гоняю Render / Effects / Subscribe / Original Fidelity тесты…"
chmod +x scripts/validate-release-8-25.sh scripts/validate-release-8-27.sh
scripts/validate-release-8-25.sh "$FFMPEG" "$FFPROBE"
scripts/validate-release-8-27.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs

echo "8/10  Все release-gates пройдены."

echo "9/10  Собираю ENDLUME Studio.app…"
npx tauri build --target aarch64-apple-darwin --bundles app --config src-tauri/tauri.local.conf.json
BUILT_APP="src-tauri/target/aarch64-apple-darwin/release/bundle/macos/ENDLUME Studio.app"
[[ -d "$BUILT_APP" ]] || fail "Tauri не создал ENDLUME Studio.app."
BUNDLE_ID="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$BUILT_APP/Contents/Info.plist")"
BUILT_VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$BUILT_APP/Contents/Info.plist")"
[[ "$BUNDLE_ID" == "studio.endlume.desktop" ]] || fail "Неверный bundle ID: $BUNDLE_ID"
[[ "$BUILT_VERSION" == "$VERSION" ]] || fail "Версия app $BUILT_VERSION не совпадает с $VERSION"
find "$BUILT_APP/Contents/MacOS" -maxdepth 1 -type f \( -name 'ffmpeg*' -o -name 'ffprobe*' \) -exec /bin/chmod 755 {} +
BUNDLED_FFMPEG="$(find "$BUILT_APP/Contents/MacOS" -maxdepth 1 -type f -name 'ffmpeg*' | head -1)"
BUNDLED_FFPROBE="$(find "$BUILT_APP/Contents/MacOS" -maxdepth 1 -type f -name 'ffprobe*' | head -1)"
[[ -n "$BUNDLED_FFMPEG" && -x "$BUNDLED_FFMPEG" ]] || fail "FFmpeg в app не исполняемый."
[[ -n "$BUNDLED_FFPROBE" && -x "$BUNDLED_FFPROBE" ]] || fail "FFprobe в app не исполняемый."
"$BUNDLED_FFMPEG" -hide_banner -version >/dev/null
"$BUNDLED_FFPROBE" -hide_banner -version >/dev/null
/usr/bin/codesign --force --deep --sign - "$BUILT_APP" >/dev/null 2>&1
/usr/bin/codesign --verify --deep --strict "$BUILT_APP" >/dev/null 2>&1 || fail "Локальная подпись не прошла проверку."

echo "10/10 Устанавливаю поверх единственной ENDLUME Studio…"
osascript -e 'tell application "ENDLUME Studio" to quit' >/dev/null 2>&1 || true
sleep 1
pkill -x "ENDLUME Studio" >/dev/null 2>&1 || true
if [[ -w /Applications ]]; then
  /bin/rm -rf "$DEST"
  /usr/bin/ditto "$BUILT_APP" "$DEST"
  /usr/bin/xattr -dr com.apple.quarantine "$DEST" >/dev/null 2>&1 || true
else
  sudo /bin/rm -rf "$DEST"
  sudo /usr/bin/ditto "$BUILT_APP" "$DEST"
  sudo /usr/bin/xattr -dr com.apple.quarantine "$DEST" >/dev/null 2>&1 || true
fi
[[ -d "$DEST" ]] || fail "Приложение не появилось в /Applications."
FINAL_VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$DEST/Contents/Info.plist")"
[[ "$FINAL_VERSION" == "$VERSION" ]] || fail "Установилась неверная версия: $FINAL_VERSION"
INSTALLED_FFMPEG="$(find "$DEST/Contents/MacOS" -maxdepth 1 -type f -name 'ffmpeg*' | head -1)"
INSTALLED_FFPROBE="$(find "$DEST/Contents/MacOS" -maxdepth 1 -type f -name 'ffprobe*' | head -1)"
[[ -x "$INSTALLED_FFMPEG" && -x "$INSTALLED_FFPROBE" ]] || fail "После установки потерялись права FFmpeg/FFprobe."
"$INSTALLED_FFMPEG" -hide_banner -version >/dev/null
"$INSTALLED_FFPROBE" -hide_banner -version >/dev/null

rm -rf "$HOME/Library/Caches/studio.endlume.desktop/render-work" >/dev/null 2>&1 || true
open "$DEST"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ENDLUME Studio $VERSION установлена"
echo "✅ Original Fidelity: low-bitrate clamp отключён"
echo "✅ Apple Silicon: HEVC VideoToolbox quality-first"
echo "✅ Compatible MP3: bitstream-copy без перекодирования"
echo "✅ Mismatched audio: ALAC lossless fallback, не AAC"
echo "✅ Effects/Subscribe: lossless chromakey cache + aspect safe"
echo "✅ Final mux: stream-copy"
echo "✅ GitHub Actions не запускались"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
osascript -e 'display notification "Original Fidelity установлен" with title "ENDLUME Studio" subtitle "1.0.0-alpha.8.27"' >/dev/null 2>&1 || true
