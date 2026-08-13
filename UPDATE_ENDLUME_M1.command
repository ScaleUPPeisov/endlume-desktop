#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
TARGET="aarch64-apple-darwin"
DESKTOP_APP="$HOME/Desktop/ENDLUME Studio.app"
LOG_DIR="$SCRIPT_DIR/build_logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ENDLUME-alpha8_3-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

fail(){
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "❌ ENDLUME: обновление остановлено"
  echo "Лог: $LOG"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  read "?Нажмите Enter, чтобы закрыть..."
  exit 1
}
trap fail ERR

printf '\033c'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ENDLUME Studio 1.0.0-alpha.8.3 — M1 Update"
echo " 13.08.2026 • Smart Size ≈ 1 GB • Fixed Project Bar"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

export PATH="/opt/homebrew/bin:$HOME/.cargo/bin:$PATH"
echo "[1/7] Проверяю MacBook / инструменты..."
[[ "$(uname -m)" == "arm64" ]] || { echo "Эта сборка рассчитана на Apple Silicon M1+"; exit 1; }
for c in node npm cargo ffmpeg ffprobe; do command -v "$c" >/dev/null || { echo "Не найден $c"; exit 1; }; done

PREV_PROJECT=""
for d in "$HOME"/Downloads/ENDLUME_1.0_Tauri*; do
  [[ -d "$d" && "$d" != "$SCRIPT_DIR" ]] || continue
  if [[ -d "$d/node_modules" || -d "$d/src-tauri/target" ]]; then PREV_PROJECT="$d"; fi
done

echo "[2/7] Переиспользую уже установленные зависимости..."
if [[ ! -e "$SCRIPT_DIR/node_modules" && -n "$PREV_PROJECT" && -d "$PREV_PROJECT/node_modules" ]]; then
  ln -s "$PREV_PROJECT/node_modules" "$SCRIPT_DIR/node_modules"
  echo "✓ node_modules: $PREV_PROJECT"
fi
if [[ ! -d "$SCRIPT_DIR/node_modules" ]]; then npm install --no-audit --no-fund; fi
if [[ -n "$PREV_PROJECT" && -d "$PREV_PROJECT/src-tauri/target" ]]; then
  export CARGO_TARGET_DIR="$PREV_PROJECT/src-tauri/target"
  echo "✓ Cargo cache: $CARGO_TARGET_DIR"
else
  export CARGO_TARGET_DIR="$SCRIPT_DIR/src-tauri/target"
fi

echo "[3/7] Готовлю встроенные FFmpeg / FFprobe..."
mkdir -p src-tauri/binaries
cp "$(command -v ffmpeg)" "src-tauri/binaries/ffmpeg-$TARGET"
cp "$(command -v ffprobe)" "src-tauri/binaries/ffprobe-$TARGET"
chmod +x "src-tauri/binaries/ffmpeg-$TARGET" "src-tauri/binaries/ffprobe-$TARGET"

echo "[4/7] Генерирую новую full-bleed иконку ENDLUME..."
npx tauri icon app-icon.png >/dev/null

echo "[5/7] TypeScript + Rust preflight..."
if grep -RInE 'useRef<[^>]+>\(\)|useRef\(\)' src > /tmp/endlume_empty_useref.txt 2>/dev/null; then
  echo "Найдены пустые useRef():"; cat /tmp/endlume_empty_useref.txt; exit 1
fi
npm run build
cargo check --manifest-path src-tauri/Cargo.toml --target "$TARGET"

echo "[6/7] Smart Size self-test 4K/60..."
SELF_DIR="$TMPDIR/endlume-alpha8_3-selftest"
rm -rf "$SELF_DIR" && mkdir -p "$SELF_DIR"
ffmpeg -hide_banner -loglevel error -f lavfi -i "testsrc2=s=3840x2160:r=1" -frames:v 1 -y "$SELF_DIR/frame.png"
START=$(date +%s)
ffmpeg -hide_banner -loglevel error -loop 1 -framerate 60 -i "$SELF_DIR/frame.png" -t 12 \
  -vf "fps=60,setsar=1" -an -c:v libx264 -preset ultrafast -tune stillimage \
  -b:v 620k -maxrate 20M -bufsize 100M -g 720 -keyint_min 720 -sc_threshold 0 \
  -pix_fmt yuv420p -x264-params 'vbv-init=1:zones=0,0,q=14' -y "$SELF_DIR/master.mp4"
MASTER_SEC=$(( $(date +%s) - START ))
VBIT=$(ffprobe -v error -select_streams v:0 -show_entries stream=bit_rate -of default=nw=1:nk=1 "$SELF_DIR/master.mp4" | tr -dc '0-9')
ffmpeg -hide_banner -loglevel error -ss 0.05 -i "$SELF_DIR/master.mp4" -frames:v 1 -y "$SELF_DIR/start.png"
SSIM=$(ffmpeg -hide_banner -i "$SELF_DIR/frame.png" -i "$SELF_DIR/start.png" -lavfi ssim -f null - 2>&1 | sed -n 's/.*All:\([0-9.]*\).*/\1/p' | tail -1)
PROJECTED=$(awk -v b="${VBIT:-0}" 'BEGIN{printf "%.3f", ((b+320000)*7200/8)/1000000000}')
echo "✓ Smart Size master: ${MASTER_SEC}s • video bitrate ${VBIT:-0} bit/s • projected 2h ${PROJECTED} GB • SSIM=${SSIM:-?}"
if [[ -n "${SSIM:-}" ]]; then awk "BEGIN{exit !($SSIM >= 0.98)}" || { echo "Качество self-test ниже 0.98: $SSIM"; exit 1; }; fi
awk -v g="$PROJECTED" 'BEGIN{exit !(g <= 1.30)}' || { echo "Smart Size превысил 1.30 GB в self-test: $PROJECTED"; exit 1; }
ffmpeg -hide_banner -loglevel error -f lavfi -i "color=c=black:s=640x360:r=30" -t 0.3 -an -c:v h264_videotoolbox -f null - >/dev/null 2>&1 && echo "✓ h264_videotoolbox доступен" || echo "⚠ VideoToolbox недоступен — видео-режимы используют fallback"
if ffmpeg -hide_banner -loglevel error -f lavfi -i "sine=frequency=440:sample_rate=48000" -t 0.5 -c:a aac_at -b:a 320k -aac_at_mode cvbr -aac_at_quality 2 -ar 48000 -ac 2 -y "$SELF_DIR/audio.m4a" 2>/dev/null; then echo "✓ AudioToolbox AAC 320k работает"; else echo "⚠ aac_at недоступен — FFmpeg AAC fallback"; fi
rm -rf "$SELF_DIR"

echo "[7/7] Собираю самостоятельный ENDLUME Studio.app..."
npx tauri build --debug --target "$TARGET" --bundles app
APP_PATH="$(find "$CARGO_TARGET_DIR" -type d -path '*/debug/bundle/macos/ENDLUME Studio.app' -print -quit 2>/dev/null || true)"
[[ -n "$APP_PATH" && -d "$APP_PATH" ]] || APP_PATH="$(find "$CARGO_TARGET_DIR" -type d -name 'ENDLUME Studio.app' -print -quit 2>/dev/null || true)"
[[ -n "$APP_PATH" && -d "$APP_PATH" ]] || { echo "Не найден собранный ENDLUME Studio.app"; exit 1; }
rm -rf "$DESKTOP_APP"
ditto "$APP_PATH" "$DESKTOP_APP"
xattr -dr com.apple.quarantine "$DESKTOP_APP" 2>/dev/null || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ENDLUME 1.0.0-alpha.8.3 УСТАНОВЛЕН"
echo "Дата обновления: 13.08.2026"
echo "Smart Size: около 1 ГБ / 2 часа для статичного 4K"
echo "Приложение: $DESKTOP_APP"
echo "Лог: $LOG"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
open "$DESKTOP_APP"
sleep 2
exit 0
