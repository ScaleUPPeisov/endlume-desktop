#!/bin/bash
set -Eeuo pipefail

APP_NAME="ENDLUME Studio"
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
  osascript -e 'display dialog "ENDLUME Studio не собрана. Подробности сохранены на Рабочем столе в ENDLUME-local-build.log" buttons {"OK"} default button "OK" with icon stop' >/dev/null 2>&1 || true
  exit 1
}
trap 'fail "Ошибка на строке $LINENO. Команда: $BASH_COMMAND"' ERR

banner(){
  clear
  echo "╭──────────────────────────────────────────────────────╮"
  echo "│               ENDLUME Studio LOCAL BUILD             │"
  echo "│ Smart Align • Aspect Safe • Render Recovery • M1+   │"
  echo "╰──────────────────────────────────────────────────────╯"
  echo
}

repair_and_remove(){
  local p="$1"
  [[ -e "$p" ]] || return 0
  /bin/rm -rf "$p" >/dev/null 2>&1 && return 0
  echo "Исправляю права старого локального build-кэша: $p"
  sudo /usr/bin/chflags -R nouchg "$p" >/dev/null 2>&1 || true
  sudo /usr/bin/chown -R "$(id -un)":staff "$p" >/dev/null 2>&1 || true
  sudo /bin/chmod -RN "$p" >/dev/null 2>&1 || true
  sudo /bin/chmod -R u+rwX "$p" >/dev/null 2>&1 || true
  sudo /bin/rm -rf "$p" || fail "Не удалось очистить старый build-кэш: $p"
}

repair_permissions(){
  local p="$1"
  [[ -e "$p" ]] || return 0
  if [[ -w "$p" ]]; then return 0; fi
  echo "Исправляю права build-кэша без удаления: $p"
  sudo /usr/bin/chflags -R nouchg "$p" >/dev/null 2>&1 || true
  sudo /usr/bin/chown -R "$(id -un)":staff "$p" >/dev/null 2>&1 || true
  sudo /bin/chmod -RN "$p" >/dev/null 2>&1 || true
  sudo /bin/chmod -R u+rwX "$p" >/dev/null 2>&1 || true
}

banner

echo "1/10  Проверяю Mac…"
[[ "$(uname -s)" == "Darwin" ]] || fail "Этот builder предназначен только для macOS."
[[ "$(uname -m)" == "arm64" ]] || fail "Нужен Mac Apple Silicon M1/M2/M3/M4/M5 или новее."

if ! xcode-select -p >/dev/null 2>&1; then
  echo "Устанавливаю Apple Command Line Tools…"
  xcode-select --install || true
  fail "После завершения установки Command Line Tools запусти этот файл ещё раз."
fi

echo "2/10  Проверяю Homebrew и инструменты…"
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew не найден. Запускаю официальную установку…"
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
if [[ -x /opt/homebrew/bin/brew ]]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
command -v brew >/dev/null 2>&1 || fail "Homebrew не установился."

brew list node@22 >/dev/null 2>&1 || brew install node@22
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
brew list ffmpeg >/dev/null 2>&1 || brew install ffmpeg
brew list librsvg >/dev/null 2>&1 || brew install librsvg
brew list gh >/dev/null 2>&1 || brew install gh

if ! command -v cargo >/dev/null 2>&1; then
  echo "Устанавливаю Rust…"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
fi
[[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env"
command -v cargo >/dev/null 2>&1 || fail "Rust/Cargo не найден."
rustup target add aarch64-apple-darwin >/dev/null

if ! gh auth status -h github.com >/dev/null 2>&1; then
  echo
  echo "3/10  Один раз авторизуй GitHub в браузере. Это НЕ запускает GitHub Actions."
  gh auth login -h github.com -p https -w
fi

echo "3/10  Получаю свежие исходники ENDLUME без GitHub Actions…"
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
repair_permissions "$SRC/src-tauri/target"

VERSION="$(node -p "require('./package.json').version")"
echo "Собираю ENDLUME Studio $VERSION"
[[ "$VERSION" == "1.0.0-alpha.8.24" ]] || fail "Ожидалась версия 1.0.0-alpha.8.24, получена $VERSION"

echo "4/10  Устанавливаю frontend-зависимости…"
npm install --no-audit --no-fund

echo "5/10  Готовлю FFmpeg/FFprobe внутри приложения…"
BIN_DIR="$SRC/src-tauri/binaries"
FFMPEG="$BIN_DIR/ffmpeg-aarch64-apple-darwin"
FFPROBE="$BIN_DIR/ffprobe-aarch64-apple-darwin"
mkdir -p "$BIN_DIR"
/usr/bin/install -m 755 "$(command -v ffmpeg)" "$FFMPEG"
/usr/bin/install -m 755 "$(command -v ffprobe)" "$FFPROBE"
[[ -x "$FFMPEG" ]] || fail "FFmpeg не удалось встроить в приложение."
[[ -x "$FFPROBE" ]] || fail "FFprobe не удалось встроить в приложение."
"$FFMPEG" -hide_banner -encoders > /tmp/endlume-local-encoders.txt
grep -q 'h264_videotoolbox' /tmp/endlume-local-encoders.txt || fail "В FFmpeg отсутствует Apple VideoToolbox."
grep -q 'libx264' /tmp/endlume-local-encoders.txt || fail "В FFmpeg отсутствует libx264 fallback."

echo "6/10  Применяю Render / Effects / Subscribe / Smart Align…"
python3 scripts/apply-render-loop-fix.py
python3 scripts/apply-render-hotfix-8-17.py
python3 scripts/apply-editor-hotfix-8-18.py
python3 scripts/apply-aspect-permission-hotfix-8-20.py
python3 scripts/apply-smart-align-hotfix-8-24.py
python3 scripts/apply-smart-align-postfix-8-24.py

grep -Fq 'refresh_project_paths(&mut resolved_job)' src-tauri/src/render.rs || fail "Не применилось восстановление путей проекта."
grep -Fq 'aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo' src-tauri/src/render.rs || fail "Не применилось исправление MP3-аудио."
grep -Fq 'scale={}:-2' src-tauri/src/render.rs || fail "Не применилось сохранение пропорций Effects."
grep -Fq 'resolve_output_dir(app,&requested_out_dir)' src-tauri/src/render.rs || fail "Не применилось восстановление прав папки результата."
grep -Fq 'effects-v4-aspect-safe' src-tauri/src/cache.rs || fail "Не применился aspect-safe chromakey cache."
grep -Fq 'overlayAspect' src/components/LiveCompositePreview.tsx || fail "Live Preview не читает исходные пропорции эффекта."
grep -Fq 'smartAlignToolbar' src/pages/Editors.tsx || fail "Smart Align toolbar не применился."
grep -Fq 'smartGuideLayer' src/pages/Editors.tsx || fail "Направляющие не применились."
grep -Fq 'smartTimingSummary' src/pages/Editors.tsx || fail "Метки Начало/Середина/Конец не применились."
grep -Fq "import './smart-align.css'" src/main.tsx || fail "Smart Align CSS не подключён."
grep -Fq 'x:.5,y:.5,firstAtSec' src/pages/Editors.tsx || fail "Subscribe не автоцентрируется при добавлении."

echo "6.5/10 Проверяю TypeScript уже с Smart Align…"
npx tsc --noEmit

echo "6.6/10 Проверяю production frontend…"
npm run build

echo "6.7/10 Проверяю Rust ДО долгих FFmpeg-тестов…"
cargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin

echo "7/10  Проверяю реальные сценарии рендера…"
chmod +x scripts/validate-loop-modes.sh
scripts/validate-loop-modes.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs

echo "8/10  Frontend + Rust + Render + Smart Align regression пройдены."

echo "9/10  Собираю ENDLUME Studio.app локально…"
npx tauri build --target aarch64-apple-darwin --bundles app --config src-tauri/tauri.local.conf.json

BUILT_APP="src-tauri/target/aarch64-apple-darwin/release/bundle/macos/ENDLUME Studio.app"
[[ -d "$BUILT_APP" ]] || fail "Сборка завершилась без ENDLUME Studio.app."
BUNDLE_ID="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$BUILT_APP/Contents/Info.plist")"
BUILT_VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$BUILT_APP/Contents/Info.plist")"
[[ "$BUNDLE_ID" == "studio.endlume.desktop" ]] || fail "Неверный bundle ID: $BUNDLE_ID"
[[ "$BUILT_VERSION" == "$VERSION" ]] || fail "Версия app ($BUILT_VERSION) не совпадает с source ($VERSION)."

find "$BUILT_APP/Contents/MacOS" -maxdepth 1 -type f \( -name 'ffmpeg*' -o -name 'ffprobe*' \) -exec /bin/chmod 755 {} +
BUNDLED_FFMPEG="$(find "$BUILT_APP/Contents/MacOS" -maxdepth 1 -type f -name 'ffmpeg*' | head -1)"
BUNDLED_FFPROBE="$(find "$BUILT_APP/Contents/MacOS" -maxdepth 1 -type f -name 'ffprobe*' | head -1)"
[[ -n "$BUNDLED_FFMPEG" && -x "$BUNDLED_FFMPEG" ]] || fail "FFmpeg в готовой ENDLUME Studio.app не исполняемый."
[[ -n "$BUNDLED_FFPROBE" && -x "$BUNDLED_FFPROBE" ]] || fail "FFprobe в готовой ENDLUME Studio.app не исполняемый."
"$BUNDLED_FFMPEG" -hide_banner -version >/dev/null || fail "FFmpeg внутри готовой app не запускается."
"$BUNDLED_FFPROBE" -hide_banner -version >/dev/null || fail "FFprobe внутри готовой app не запускается."

/usr/bin/codesign --force --deep --sign - "$BUILT_APP" >/dev/null 2>&1 || fail "Не удалось выполнить локальную подпись app."
/usr/bin/codesign --verify --deep --strict "$BUILT_APP" >/dev/null 2>&1 || fail "Проверка локальной подписи не прошла."

echo "10/10 Устанавливаю поверх текущей ENDLUME Studio — без второй копии…"
osascript -e 'tell application "ENDLUME Studio" to quit' >/dev/null 2>&1 || true
sleep 1
pkill -x "ENDLUME Studio" >/dev/null 2>&1 || true

if [[ -w /Applications ]]; then
  /bin/rm -rf "$DEST"
  /usr/bin/ditto "$BUILT_APP" "$DEST"
  /usr/bin/xattr -dr com.apple.quarantine "$DEST" >/dev/null 2>&1 || true
else
  echo "macOS попросит пароль администратора один раз для замены приложения в /Applications."
  sudo /bin/rm -rf "$DEST"
  sudo /usr/bin/ditto "$BUILT_APP" "$DEST"
  sudo /usr/bin/xattr -dr com.apple.quarantine "$DEST" >/dev/null 2>&1 || true
fi

[[ -d "$DEST" ]] || fail "ENDLUME Studio.app не появилась в /Applications."
FINAL_VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$DEST/Contents/Info.plist")"
[[ "$FINAL_VERSION" == "$VERSION" ]] || fail "После установки обнаружена неверная версия: $FINAL_VERSION"
INSTALLED_FFMPEG="$(find "$DEST/Contents/MacOS" -maxdepth 1 -type f -name 'ffmpeg*' | head -1)"
INSTALLED_FFPROBE="$(find "$DEST/Contents/MacOS" -maxdepth 1 -type f -name 'ffprobe*' | head -1)"
[[ -n "$INSTALLED_FFMPEG" && -x "$INSTALLED_FFMPEG" ]] || fail "У установленной ENDLUME потерялись права запуска FFmpeg."
[[ -n "$INSTALLED_FFPROBE" && -x "$INSTALLED_FFPROBE" ]] || fail "У установленной ENDLUME потерялись права запуска FFprobe."
"$INSTALLED_FFMPEG" -hide_banner -version >/dev/null || fail "Установленный FFmpeg не запускается — Render получил бы Permission denied."
"$INSTALLED_FFPROBE" -hide_banner -version >/dev/null || fail "Установленный FFprobe не запускается."

open "$DEST"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ENDLUME Studio $VERSION установлена"
echo "✅ Effects/Subscribe сохраняют оригинальные пропорции"
echo "✅ Автоцентр для новых Effects/Subscribe"
echo "✅ Smart Snap + центр/края + Safe Area"
echo "✅ Точные X/Y/SIZE + стрелки + Shift bypass"
echo "✅ Timeline: Начало / Середина / Конец / Длительность"
echo "✅ Render permission recovery"
echo "✅ Loop Mode: 100/100"
echo "✅ GitHub Actions не запускались"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
osascript -e "display dialog \"ENDLUME Studio $VERSION установлена. Smart Align, направляющие и метки времени готовы.\" buttons {\"Открыть ENDLUME\"} default button \"Открыть ENDLUME\" with icon note" >/dev/null 2>&1 || true
