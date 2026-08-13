#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != "Darwin" ]]; then echo "ERROR: DMG must be built on macOS."; exit 1; fi
if [[ "$(uname -m)" != "arm64" ]]; then echo "ERROR: This script targets Apple Silicon (M1+)."; exit 1; fi
command -v node >/dev/null || { echo "Install Node.js 20+"; exit 1; }
command -v rustc >/dev/null || { echo "Rust missing. Install with rustup, then rerun."; exit 1; }
TARGET=aarch64-apple-darwin
mkdir -p src-tauri/binaries
for b in ffmpeg ffprobe; do
  src="vendor/macos-arm64/$b"
  dst="src-tauri/binaries/$b-$TARGET"
  [[ -x "$src" ]] || { echo "Missing bundled $src"; exit 1; }
  cp "$src" "$dst"; chmod +x "$dst"
done
npm install
npm run tauri build -- --target "$TARGET" --bundles app,dmg
