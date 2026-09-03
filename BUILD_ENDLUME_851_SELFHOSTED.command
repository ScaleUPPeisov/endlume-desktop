#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_850_SELFHOSTED.command"
PATCH_REF="${ENDLUME_851_PATCH_REF:-candidate/full-project-speed-8.51}"
FINAL_ART="${ENDLUME_RELEASE_ARTIFACT_DIR:-$HOME/.endlume-release-bridge/endlume/current}"
FINAL_VERSION="${ENDLUME_RELEASE_VERSION:-1.0.0-alpha.8.51}"
TMP="$(mktemp -d /tmp/endlume-851-builder.XXXXXX)"
BASE_ART="$TMP/base-850-artifacts"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo "❌ ENDLUME 8.51 BUILDER: $1" >&2; exit 1; }

[[ -f "$BASE" ]] || fail "8.50 builder missing"
[[ "$FINAL_VERSION" = "1.0.0-alpha.8.51" ]] || fail "release version must be 1.0.0-alpha.8.51, got $FINAL_VERSION"
mkdir -p "$BASE_ART" "$FINAL_ART"

# Reconstruct the exact stable 8.50 foundation first.
export ENDLUME_RELEASE_ARTIFACT_DIR="$BASE_ART"
export ENDLUME_RELEASE_VERSION="1.0.0-alpha.8.50"
export ENDLUME_850_PATCH_REF="release"
chmod +x "$BASE"
/bin/bash "$BASE"

WORK="$HOME/.endlume-local-builder/endlume-desktop-8.40-bootstrap"
[[ -f "$WORK/src-tauri/src/render.rs" ]] || fail "8.50 effective workspace missing"
FFMPEG="$(find "$WORK/src-tauri/binaries" -maxdepth 1 -type f -name 'ffmpeg*' -print -quit)"
FFPROBE="$(find "$WORK/src-tauri/binaries" -maxdepth 1 -type f -name 'ffprobe*' -print -quit)"
[[ -x "$FFMPEG" ]] || fail "embedded FFmpeg missing"
[[ -x "$FFPROBE" ]] || fail "embedded FFprobe missing"

echo "✅ 8.50 foundation reconstructed; applying 8.51 FULL PROJECT SPEED from ref=$PATCH_REF"
mkdir -p "$WORK/scripts"
GH_REPO="ScaleUPPeisov/endlume-desktop"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$GH_REPO/contents/scripts/apply-full-project-speed-8-51.py?ref=$PATCH_REF" > "$WORK/scripts/apply-full-project-speed-8-51.py" || fail "cannot fetch 8.51 migration"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$GH_REPO/contents/scripts/validate-release-8-51.sh?ref=$PATCH_REF" > "$WORK/scripts/validate-release-8-51.sh" || fail "cannot fetch 8.51 validator"
python3 -m py_compile "$WORK/scripts/apply-full-project-speed-8-51.py"
/bin/bash -n "$WORK/scripts/validate-release-8-51.sh"
chmod +x "$WORK/scripts/validate-release-8-51.sh"
python3 "$WORK/scripts/apply-full-project-speed-8-51.py" "$WORK"
"$WORK/scripts/validate-release-8-51.sh" "$WORK" "$FFMPEG" "$FFPROBE"

cd "$WORK"
echo '@@ENDLUME_STAGE|8.51/10 Проверяю full-project 20–30s / whole-track / watchdog'
echo '@@ENDLUME_PROGRESS|74'
npm run check
npm run build
cargo test --manifest-path src-tauri/Cargo.toml manifest_851_tests -- --nocapture
cargo test --manifest-path src-tauri/Cargo.toml audio_timeline_849_tests -- --nocapture
cargo test --manifest-path src-tauri/Cargo.toml watchdog_tests -- --nocapture
cargo check --manifest-path src-tauri/Cargo.toml

echo '@@ENDLUME_STAGE|9/10 Собираю ENDLUME STUDIO PEISOV 8.51'
echo '@@ENDLUME_PROGRESS|85'
export ENDLUME_RELEASE_ARTIFACT_DIR="$FINAL_ART"
export ENDLUME_RELEASE_VERSION="1.0.0-alpha.8.51"
rm -rf src-tauri/target/aarch64-apple-darwin/release/bundle/macos
npx tauri build --target aarch64-apple-darwin --bundles app

BUNDLE="$WORK/src-tauri/target/aarch64-apple-darwin/release/bundle/macos"
APP="$(find "$BUNDLE" -maxdepth 1 -type d -name '*.app' -print -quit)"
TAR="$(find "$BUNDLE" -maxdepth 1 -type f -name '*.app.tar.gz' -print -quit)"
[[ -n "$APP" && -d "$APP" ]] || fail "8.51 .app missing"
[[ "$(basename "$APP")" = "ENDLUME STUDIO PEISOV.app" ]] || fail "wrong app display bundle"
[[ -n "$TAR" ]] || TAR="$BUNDLE/ENDLUME STUDIO PEISOV.app.tar.gz"

ID="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$APP/Contents/Info.plist")"
VER="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$APP/Contents/Info.plist")"
EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$APP/Contents/Info.plist")"
[[ "$ID" = "studio.endlume.desktop" ]] || fail "bundle identifier changed: $ID"
[[ "$VER" = "1.0.0-alpha.8.51" ]] || fail "bundle version mismatch: $VER"
/usr/bin/lipo -archs "$APP/Contents/MacOS/$EXE" | grep -qw arm64 || fail "main executable is not arm64"

if ! /usr/bin/codesign --verify --deep --strict "$APP" >/dev/null 2>&1; then
  /usr/bin/codesign --force --deep --sign - "$APP" || fail "macOS bundle seal failed"
fi
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP" || fail "strict codesign failed"
[[ -s "$APP/Contents/_CodeSignature/CodeResources" ]] || fail "CodeResources missing"

rm -f "$TAR" "$TAR.sig"
/usr/bin/tar -czf "$TAR" -C "$BUNDLE" "$(basename "$APP")" || fail "cannot recreate updater tar"
[[ -s "$TAR" ]] || fail "updater tar missing"
env -u TAURI_SIGNING_PRIVATE_KEY npx tauri signer sign "$TAR" >/dev/null || fail "Tauri updater signature failed"
[[ -s "$TAR.sig" ]] || fail "updater signature missing"

VERIFY="$TMP/verify"
mkdir -p "$VERIFY"
/usr/bin/tar -xzf "$TAR" -C "$VERIFY" || fail "cannot unpack updater tar"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$VERIFY/ENDLUME STUDIO PEISOV.app" || fail "archive app signature invalid"

rm -rf "$FINAL_ART"
mkdir -p "$FINAL_ART"
cp "$TAR" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz"
cp "$TAR.sig" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz.sig"
printf '%s\n' '1.0.0-alpha.8.51' > "$FINAL_ART/version.txt"

grep -Fq 'VISUAL_PLAN_CACHE_GENERATION:&str="8.51-manifest-v1"' src-tauri/src/render.rs || fail "8.51 manifest generation lost"
grep -Fq '8.51 MANIFEST_READY' src-tauri/src/render.rs || fail "manifest speed path lost"
grep -Fq 'attempt==1&&encoder_works(app,"hevc_videotoolbox")' src-tauri/src/render.rs || fail "hardware-first selector lost"
grep -Fq '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"' src-tauri/src/render.rs || fail "q100 fidelity profile lost"
grep -Fq 'let idx=i%durations.len();' src-tauri/src/render.rs || fail "whole-track math lost"
if grep -Fq 'if t-target<=240.0{t}else{target}' src-tauri/src/render.rs; then fail "song cut cap returned"; fi

echo '@@ENDLUME_PROGRESS|100'
echo '✅ ENDLUME STUDIO PEISOV 8.51 candidate ready'
echo '✅ full-project manifest-only assembly; no duplicate multi-minute normal visual files'
echo '✅ VideoToolbox q100 / 500k / 1920x1080 / whole-track preserved'
echo '✅ signed updater archive contains strict-valid ENDLUME STUDIO PEISOV.app'
# candidate trigger: full-project gate required before any stable promotion
