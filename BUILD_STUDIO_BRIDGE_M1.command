#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PATH="/opt/homebrew/bin:$HOME/.cargo/bin:$PATH"
echo "ENDLUME Studio Bridge — отдельная тестовая сборка для VYRON AI STUDIO"
echo "Стабильный ENDLUME Studio.app не удаляется и не заменяется."
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then echo "Нужен Mac Apple Silicon"; exit 1; fi
for tool in node npm cargo ffmpeg ffprobe; do
 if ! command -v "$tool" >/dev/null 2>&1; then
   echo "Отсутствует $tool — установить заранее, проверка остановлена."; exit 1
 fi
done
if pgrep -f '/ENDLUME Studio.app/Contents/MacOS/' >/dev/null 2>&1; then
 echo "Закрой стабильную ENDLUME Studio перед запуском тестового моста. Параллельно они могут затронуть общую очередь."
 exit 1
fi
mkdir -p src-tauri/binaries
for binary in ffmpeg ffprobe; do
 cp "$(command -v "$binary")" "src-tauri/binaries/${binary}-aarch64-apple-darwin"
 chmod +x "src-tauri/binaries/${binary}-aarch64-apple-darwin"
done
if [[ -f package-lock.json ]]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
npx tauri icon app-icon.png >/dev/null
cargo check --manifest-path src-tauri/Cargo.toml
cargo test --manifest-path src-tauri/Cargo.toml studio_bridge::tests
npx tauri build --debug --target aarch64-apple-darwin --bundles app
APP_SRC="$(find "$ROOT/src-tauri/target" -type d -path '*/debug/bundle/macos/ENDLUME Studio.app' -print -quit 2>/dev/null || true)"
[[ -n "$APP_SRC" ]] || { echo "Сборка не найдена. Ничего не заменено."; exit 1; }
DEST="$HOME/Desktop/ENDLUME Studio Bridge.app"
if [[ -e "$DEST" ]]; then
  echo "Уже существует $DEST. Сначала вручную перемести старую тестовую сборку."
  exit 1
fi
ditto "$APP_SRC" "$DEST"
echo ""
echo "Готово: $DEST"
echo "Это отдельная тестовая сборка; стабильная версия осталась на месте."
echo "Не запускай обе ENDLUME одновременно: они используют один bundle ID и данные очереди."
echo "При первом запуске macOS может запросить разрешение на открытие неподписанного приложения."
read -r "?Нажми Enter для завершения: " _
