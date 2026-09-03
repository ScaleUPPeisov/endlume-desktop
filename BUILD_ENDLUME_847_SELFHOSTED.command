#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_846_SELFHOSTED.command"
PATCH_REF="${ENDLUME_847_PATCH_REF:-release}"
FINAL_ART="${ENDLUME_RELEASE_ARTIFACT_DIR:-$HOME/.endlume-release-bridge/endlume/current}"
FINAL_VERSION="${ENDLUME_RELEASE_VERSION:-1.0.0-alpha.8.47}"
TMP="$(mktemp -d /tmp/endlume-847-builder.XXXXXX)"
BASE_ART="$TMP/base-846-artifacts"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo "❌ ENDLUME 8.47 BUILDER: $1" >&2; exit 1; }

[[ -f "$BASE" ]] || fail "8.46 builder missing"
[[ "$FINAL_VERSION" = "1.0.0-alpha.8.47" ]] || fail "release version must be 1.0.0-alpha.8.47, got $FINAL_VERSION"
mkdir -p "$BASE_ART" "$FINAL_ART"

export ENDLUME_RELEASE_ARTIFACT_DIR="$BASE_ART"
export ENDLUME_RELEASE_VERSION="1.0.0-alpha.8.46"
chmod +x "$BASE"
/bin/bash "$BASE"

WORK="$HOME/.endlume-local-builder/endlume-desktop-8.40-bootstrap"
[[ -f "$WORK/package.json" ]] || fail "8.46 effective workspace missing: $WORK"
[[ -f "$WORK/src-tauri/src/render.rs" ]] || fail "8.46 render.rs missing"

echo "✅ 8.46 foundation reconstructed; applying 8.47 from ref=$PATCH_REF"
mkdir -p "$WORK/scripts"
GH_REPO="ScaleUPPeisov/endlume-desktop"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$GH_REPO/contents/scripts/apply-render-performance-8-47.py?ref=$PATCH_REF" > "$WORK/scripts/apply-render-performance-8-47.py" || fail "cannot fetch 8.47 migration"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$GH_REPO/contents/scripts/validate-release-8-47.sh?ref=$PATCH_REF" > "$WORK/scripts/validate-release-8-47.sh" || fail "cannot fetch 8.47 validator"
python3 -m py_compile "$WORK/scripts/apply-render-performance-8-47.py"
chmod +x "$WORK/scripts/validate-release-8-47.sh"
python3 "$WORK/scripts/apply-render-performance-8-47.py" "$WORK"

FFMPEG="$(find "$WORK/src-tauri/binaries" -maxdepth 1 -type f -name 'ffmpeg*' -print -quit)"
FFPROBE="$(find "$WORK/src-tauri/binaries" -maxdepth 1 -type f -name 'ffprobe*' -print -quit)"
[[ -x "$FFMPEG" ]] || fail "embedded FFmpeg missing"
[[ -x "$FFPROBE" ]] || fail "embedded FFprobe missing"
"$WORK/scripts/validate-release-8-47.sh" "$FFMPEG" "$FFPROBE"

cd "$WORK"
echo '@@ENDLUME_STAGE|8.47/10 Проверяю frontend/Rust после performance migration'
echo '@@ENDLUME_PROGRESS|72'
npm run check
npm run build
cargo test --manifest-path src-tauri/Cargo.toml watchdog_tests -- --nocapture
cargo check --manifest-path src-tauri/Cargo.toml

echo '@@ENDLUME_STAGE|9/10 Собираю ENDLUME Studio 8.47 hardware-first'
echo '@@ENDLUME_PROGRESS|82'
export ENDLUME_RELEASE_ARTIFACT_DIR="$FINAL_ART"
export ENDLUME_RELEASE_VERSION="1.0.0-alpha.8.47"
rm -rf src-tauri/target/aarch64-apple-darwin/release/bundle/macos
npx tauri build --target aarch64-apple-darwin --bundles app

TAR="$(find "$WORK/src-tauri/target/aarch64-apple-darwin/release/bundle/macos" -maxdepth 1 -type f -name '*.app.tar.gz' -print -quit)"
[[ -n "$TAR" && -s "$TAR" ]] || fail "8.47 updater tar missing"
[[ -s "$TAR.sig" ]] || fail "8.47 updater signature missing"
rm -rf "$FINAL_ART"
mkdir -p "$FINAL_ART"
cp "$TAR" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz"
cp "$TAR.sig" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz.sig"
printf '%s\n' '1.0.0-alpha.8.47' > "$FINAL_ART/version.txt"

grep -Fq 'attempt==1&&encoder_works(app,"hevc_videotoolbox")' src-tauri/src/render.rs || fail "hardware-first marker lost after build"
grep -Fq 'target_video_kbps=500' src-tauri/src/render.rs || fail "performance diagnostic marker lost"
python3 - <<'PY'
from pathlib import Path
s=Path('src-tauri/src/render.rs').read_text()
lines=[x for x in s.splitlines() if '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"' in x]
assert lines and all('+faststart' not in x for x in lines)
PY

echo '@@ENDLUME_PROGRESS|100'
echo '✅ ENDLUME 8.47 signed updater artifact ready'
echo '✅ M1 hardware HEVC first; CPU x265 fallback only'
echo '✅ final stream-copy mux no longer relocates entire 500–700 MB file with +faststart'
echo '✅ exact 1920x1080 / 500k budget / bounded FFprobe / watchdog preserved'
