#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
printf '\033c'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ENDLUME Studio 1.0 — macOS M1+ Builder"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
[[ "$(uname -s)" == "Darwin" ]] || { echo "Ошибка: запускать на macOS"; read -k 1; exit 1; }
[[ "$(uname -m)" == "arm64" ]] || { echo "Ошибка: эта сборка для Apple Silicon M1+"; read -k 1; exit 1; }
if ! command -v brew >/dev/null; then
  echo "[1/6] Устанавливаю Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi
if ! command -v node >/dev/null; then echo "[2/6] Устанавливаю Node.js..."; brew install node; else echo "[2/6] Node.js найден: $(node -v)"; fi
if ! command -v rustup >/dev/null; then
  echo "[3/6] Устанавливаю Rust..."; curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
fi
source "$HOME/.cargo/env" 2>/dev/null || true
rustup target add aarch64-apple-darwin >/dev/null
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then echo "[4/6] Устанавливаю FFmpeg..."; brew install ffmpeg; else echo "[4/6] FFmpeg найден"; fi
mkdir -p src-tauri/binaries vendor/macos-arm64
cp "$(command -v ffmpeg)" vendor/macos-arm64/ffmpeg
cp "$(command -v ffprobe)" vendor/macos-arm64/ffprobe
chmod +x vendor/macos-arm64/ffmpeg vendor/macos-arm64/ffprobe
cp vendor/macos-arm64/ffmpeg src-tauri/binaries/ffmpeg-aarch64-apple-darwin
cp vendor/macos-arm64/ffprobe src-tauri/binaries/ffprobe-aarch64-apple-darwin
chmod +x src-tauri/binaries/*
echo "[5/6] Устанавливаю зависимости ENDLUME..."
npm install --no-audit --no-fund
echo "[6/6] Собираю ENDLUME.app + DMG..."
npm run tauri build -- --target aarch64-apple-darwin --bundles app,dmg
OUT="$ROOT/src-tauri/target/aarch64-apple-darwin/release/bundle"
echo ""
echo "✅ Сборка завершена"
echo "DMG: $OUT/dmg"
echo "APP: $OUT/macos"
open "$OUT/dmg" || true
echo ""
echo "Для коммерческой раздачи следующим шагом подключаем Apple Developer signing + notarization."
read "?Нажмите Enter для выхода..."
