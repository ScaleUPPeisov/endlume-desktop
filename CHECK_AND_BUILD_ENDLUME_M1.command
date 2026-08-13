#!/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
mkdir -p build_logs
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$ROOT/build_logs/ENDLUME-M1-$STAMP.log"
exec > >(tee -a "$LOG") 2>&1

fail(){
  echo
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "СБОРКА ОСТАНОВЛЕНА"
  echo "$1"
  echo "Лог: $LOG"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  read -r -p "Нажмите Enter, чтобы закрыть..." _ || true
  exit 1
}
trap 'fail "Ошибка на строке $LINENO. Последняя команда: $BASH_COMMAND"' ERR

clear || true
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ENDLUME Studio 1.0.0-alpha.5 — MacBook M1 Builder"
echo " Tauri 2 + Rust + FFmpeg • Apple Silicon"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

[[ "$(uname -s)" == "Darwin" ]] || fail "Этот builder запускается только на macOS."
[[ "$(uname -m)" == "arm64" ]] || fail "Нужен Mac на Apple Silicon: M1/M2/M3/M4 или новее."

echo "[1/10] Проверяю Apple Command Line Tools..."
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Открываю установку Apple Command Line Tools."
  xcode-select --install || true
  fail "После завершения установки Command Line Tools запустите builder ещё раз."
fi

# Apple Silicon Homebrew lives here. Add it even before brew is installed.
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$HOME/.cargo/bin:$PATH"

echo "[2/10] Проверяю Homebrew..."
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew не найден. Устанавливаю официальный Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
fi
command -v brew >/dev/null 2>&1 || fail "Homebrew не установился."

echo "[3/10] Проверяю Node.js..."
if ! command -v node >/dev/null 2>&1; then brew install node; fi
NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
if [[ "$NODE_MAJOR" -lt 20 ]]; then brew upgrade node || brew install node; fi
node --version
npm --version

echo "[4/10] Проверяю Rust..."
if ! command -v rustc >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  source "$HOME/.cargo/env"
fi
rustup target add aarch64-apple-darwin
rustc --version
cargo --version

echo "[5/10] Проверяю FFmpeg / FFprobe..."
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  brew install ffmpeg
fi
ffmpeg -version | head -1
ffprobe -version | head -1
if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q 'h264_videotoolbox'; then
  echo "✓ Apple VideoToolbox доступен"
else
  echo "⚠ h264_videotoolbox не найден. ENDLUME сможет использовать CPU fallback, но это будет медленнее."
fi

TARGET="aarch64-apple-darwin"
mkdir -p src-tauri/binaries vendor/macos-arm64
cp -L "$(command -v ffmpeg)" "vendor/macos-arm64/ffmpeg"
cp -L "$(command -v ffprobe)" "vendor/macos-arm64/ffprobe"
cp -L "$(command -v ffmpeg)" "src-tauri/binaries/ffmpeg-$TARGET"
cp -L "$(command -v ffprobe)" "src-tauri/binaries/ffprobe-$TARGET"
chmod +x "vendor/macos-arm64/ffmpeg" "vendor/macos-arm64/ffprobe" "src-tauri/binaries/ffmpeg-$TARGET" "src-tauri/binaries/ffprobe-$TARGET"

echo "[6/10] Проверяю JS-зависимости..."
if [[ -d node_modules && -f package-lock.json ]]; then
  echo "✓ node_modules уже есть — повторную установку пропускаю"
elif [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi

echo "[7/10] Проверяю React/TypeScript интерфейс..."
npm run build

echo "[8/10] Проверяю Rust Engine через cargo check..."
cargo check --manifest-path src-tauri/Cargo.toml --target "$TARGET"

echo "[9/10] Проверяю ENDLUME Fast Engine..."
TEST_DIR="$ROOT/.endlume-build-test"
rm -rf "$TEST_DIR" && mkdir -p "$TEST_DIR"
ffmpeg -hide_banner -loglevel error -f lavfi -i "color=c=black:s=640x360:r=30" -t 0.4 -an -c:v h264_videotoolbox -f null - >/dev/null 2>&1 || \
ffmpeg -hide_banner -loglevel error -f lavfi -i "color=c=black:s=640x360:r=30" -t 0.4 -an -c:v libx264 -f null - >/dev/null 2>&1 || fail "FFmpeg не смог выполнить тестовый encode."
rm -rf "$TEST_DIR"

echo "[10/10] Собираю ENDLUME.app + ENDLUME.dmg..."
npm run tauri build -- --target "$TARGET" --bundles app,dmg

OUT="$ROOT/src-tauri/target/$TARGET/release/bundle"
DMG="$(find "$OUT/dmg" -maxdepth 1 -type f -name '*.dmg' -print -quit 2>/dev/null || true)"
APP="$(find "$OUT/macos" -maxdepth 1 -type d -name '*.app' -print -quit 2>/dev/null || true)"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ENDLUME M1 BUILD — ГОТОВО"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
[[ -n "$APP" ]] && echo "APP: $APP"
[[ -n "$DMG" ]] && echo "DMG: $DMG"
echo "Лог проверки: $LOG"
echo
echo "Первый запуск потребует ключ ENDLUME."
echo "Для коммерческой раздачи другим пользователям позже добавим Apple Developer signing + notarization."
open "$OUT"
read -r -p "Нажмите Enter, чтобы закрыть builder..." _ || true
