#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_847_SELFHOSTED.command"
PATCH_REF="${ENDLUME_849_PATCH_REF:-release}"
FINAL_ART="${ENDLUME_RELEASE_ARTIFACT_DIR:-$HOME/.endlume-release-bridge/endlume/current}"
FINAL_VERSION="${ENDLUME_RELEASE_VERSION:-1.0.0-alpha.8.49}"
TMP="$(mktemp -d /tmp/endlume-849-r2-builder.XXXXXX)"
BASE_ART="$TMP/base-847-artifacts"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo "❌ ENDLUME 8.49 R2 BUILDER: $1" >&2; exit 1; }

[[ -f "$BASE" ]] || fail "8.47 builder missing"
[[ "$FINAL_VERSION" = "1.0.0-alpha.8.49" ]] || fail "release version must be 1.0.0-alpha.8.49, got $FINAL_VERSION"
mkdir -p "$BASE_ART" "$FINAL_ART"

export ENDLUME_RELEASE_ARTIFACT_DIR="$BASE_ART"
export ENDLUME_RELEASE_VERSION="1.0.0-alpha.8.47"
chmod +x "$BASE"
/bin/bash "$BASE"

WORK="$HOME/.endlume-local-builder/endlume-desktop-8.40-bootstrap"
[[ -f "$WORK/package.json" ]] || fail "8.47 effective workspace missing: $WORK"
[[ -f "$WORK/src-tauri/src/render.rs" ]] || fail "8.47 render.rs missing"

echo "✅ 8.47 foundation reconstructed; applying 8.49 R2 PERFORMANCE/FIDELITY/AUDIO from ref=$PATCH_REF"
mkdir -p "$WORK/scripts"
GH_REPO="ScaleUPPeisov/endlume-desktop"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$GH_REPO/contents/scripts/apply-performance-fidelity-audio-8-49.py?ref=$PATCH_REF" > "$WORK/scripts/apply-performance-fidelity-audio-8-49.py" || fail "cannot fetch canonical 8.49 migration"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$GH_REPO/contents/scripts/apply-performance-fidelity-audio-8-49-r2.py?ref=$PATCH_REF" > "$WORK/scripts/apply-performance-fidelity-audio-8-49-r2.py" || fail "cannot fetch 8.49 R2 migration wrapper"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$GH_REPO/contents/scripts/validate-release-8-49.sh?ref=$PATCH_REF" > "$WORK/scripts/validate-release-8-49.sh" || fail "cannot fetch 8.49 validator"
python3 -m py_compile "$WORK/scripts/apply-performance-fidelity-audio-8-49.py" "$WORK/scripts/apply-performance-fidelity-audio-8-49-r2.py"
/bin/bash -n "$WORK/scripts/validate-release-8-49.sh"
chmod +x "$WORK/scripts/validate-release-8-49.sh"
python3 "$WORK/scripts/apply-performance-fidelity-audio-8-49-r2.py" "$WORK"

FFMPEG="$(find "$WORK/src-tauri/binaries" -maxdepth 1 -type f -name 'ffmpeg*' -print -quit)"
FFPROBE="$(find "$WORK/src-tauri/binaries" -maxdepth 1 -type f -name 'ffprobe*' -print -quit)"
[[ -x "$FFMPEG" ]] || fail "embedded FFmpeg missing"
[[ -x "$FFPROBE" ]] || fail "embedded FFprobe missing"
"$WORK/scripts/validate-release-8-49.sh" "$WORK" "$FFMPEG" "$FFPROBE"

cd "$WORK"
echo '@@ENDLUME_STAGE|8.49/10 Проверяю fidelity / whole-track / persistent warm cache'
echo '@@ENDLUME_PROGRESS|73'
npm run check
npm run build
cargo test --manifest-path src-tauri/Cargo.toml audio_timeline_849_tests -- --nocapture
cargo test --manifest-path src-tauri/Cargo.toml watchdog_tests -- --nocapture
cargo check --manifest-path src-tauri/Cargo.toml

echo '@@ENDLUME_STAGE|9/10 Собираю ENDLUME STUDIO PEISOV 8.49'
echo '@@ENDLUME_PROGRESS|84'
export ENDLUME_RELEASE_ARTIFACT_DIR="$FINAL_ART"
export ENDLUME_RELEASE_VERSION="1.0.0-alpha.8.49"
rm -rf src-tauri/target/aarch64-apple-darwin/release/bundle/macos
npx tauri build --target aarch64-apple-darwin --bundles app

BUNDLE="$WORK/src-tauri/target/aarch64-apple-darwin/release/bundle/macos"
APP="$(find "$BUNDLE" -maxdepth 1 -type d -name '*.app' -print -quit)"
TAR="$(find "$BUNDLE" -maxdepth 1 -type f -name '*.app.tar.gz' -print -quit)"
[[ -n "$APP" && -d "$APP" ]] || fail "8.49 .app missing"
[[ "$(basename "$APP")" = "ENDLUME STUDIO PEISOV.app" ]] || fail "wrong app display bundle: $(basename "$APP")"
[[ -n "$TAR" && -s "$TAR" ]] || fail "8.49 updater tar missing"
[[ -s "$TAR.sig" ]] || fail "8.49 updater signature missing"

ID="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$APP/Contents/Info.plist")"
VER="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$APP/Contents/Info.plist")"
EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$APP/Contents/Info.plist")"
[[ "$ID" = "studio.endlume.desktop" ]] || fail "bundle identifier changed: $ID"
[[ "$VER" = "1.0.0-alpha.8.49" ]] || fail "bundle version mismatch: $VER"
/usr/bin/lipo -archs "$APP/Contents/MacOS/$EXE" | grep -qw arm64 || fail "main executable is not arm64"
/usr/bin/codesign --verify --deep --strict "$APP" || fail "codesign verification failed"
find "$APP/Contents/MacOS" -maxdepth 1 -type f -name 'ffmpeg*' -perm +111 -print -quit | grep -q . || fail "embedded executable FFmpeg missing"
find "$APP/Contents/MacOS" -maxdepth 1 -type f -name 'ffprobe*' -perm +111 -print -quit | grep -q . || fail "embedded executable FFprobe missing"

rm -rf "$FINAL_ART"
mkdir -p "$FINAL_ART"
cp "$TAR" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz"
cp "$TAR.sig" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz.sig"
printf '%s\n' '1.0.0-alpha.8.49' > "$FINAL_ART/version.txt"

grep -Fq 'attempt==1&&encoder_works(app,"libx265")' src-tauri/src/render.rs || fail "x265 quality-first selector lost"
grep -Fq 'RENDER_CACHE_GENERATION:&str="8.49-fidelity-v1"' src-tauri/src/render.rs || fail "persistent cache marker lost"
grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' src-tauri/src/render.rs || fail "500k budget changed"
grep -Fq 'resolved_job.settings.width=1920;' src-tauri/src/render.rs || fail "1920 width lock lost"
grep -Fq 'resolved_job.settings.height=1080;' src-tauri/src/render.rs || fail "1080 height lock lost"
if grep -Fq 'if t-target<=240.0{t}else{target}' src-tauri/src/render.rs; then fail "old song truncation cap returned"; fi
grep -Fq 'FFMPEG_STALL_TIMEOUT_SECS:u64=120' src-tauri/src/render.rs || fail "watchdog marker lost"
grep -Fq 'ffprobe_output_timeout(app,args,Duration::from_secs(12))' src-tauri/src/render.rs || fail "bounded FFprobe marker lost"
grep -Fq '"productName": "ENDLUME STUDIO PEISOV"' src-tauri/tauri.conf.json || fail "brand marker lost"
grep -Fq '"identifier": "studio.endlume.desktop"' src-tauri/tauri.conf.json || fail "updater identity changed"

echo '@@ENDLUME_PROGRESS|100'
echo '✅ ENDLUME STUDIO PEISOV 8.49 signed candidate artifact ready'
echo '✅ full boundary song instead of arbitrary 2h cut'
echo '✅ x265 quality-first short master; VideoToolbox fallback only'
echo '✅ persistent visual/Subscribe/audio caches for warm 20–30s target'
echo '✅ 1920x1080 / 500k / CFR30-60 / watchdog / bounded FFprobe / updater identity preserved'
