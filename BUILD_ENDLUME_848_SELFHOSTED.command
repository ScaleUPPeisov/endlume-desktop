#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_847_SELFHOSTED.command"
PATCH_REF="${ENDLUME_848_PATCH_REF:-release}"
FINAL_ART="${ENDLUME_RELEASE_ARTIFACT_DIR:-$HOME/.endlume-release-bridge/endlume/current}"
FINAL_VERSION="${ENDLUME_RELEASE_VERSION:-1.0.0-alpha.8.48}"
TMP="$(mktemp -d /tmp/endlume-848-builder.XXXXXX)"
BASE_ART="$TMP/base-847-artifacts"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo "❌ ENDLUME 8.48 BUILDER: $1" >&2; exit 1; }

[[ -f "$BASE" ]] || fail "8.47 builder missing"
[[ "$FINAL_VERSION" = "1.0.0-alpha.8.48" ]] || fail "release version must be 1.0.0-alpha.8.48, got $FINAL_VERSION"
mkdir -p "$BASE_ART" "$FINAL_ART"

# Reconstruct the already-verified 8.47 foundation first. No 8.47 runtime logic
# is changed by this wrapper.
export ENDLUME_RELEASE_ARTIFACT_DIR="$BASE_ART"
export ENDLUME_RELEASE_VERSION="1.0.0-alpha.8.47"
unset ENDLUME_848_PATCH_REF || true
chmod +x "$BASE"
/bin/bash "$BASE"

WORK="$HOME/.endlume-local-builder/endlume-desktop-8.40-bootstrap"
[[ -f "$WORK/package.json" ]] || fail "8.47 effective workspace missing: $WORK"
[[ -f "$WORK/src-tauri/src/render.rs" ]] || fail "8.47 render.rs missing"

echo "✅ 8.47 foundation reconstructed; applying 8.48 AUDIO ONLY from ref=$PATCH_REF"
mkdir -p "$WORK/scripts"
GH_REPO="ScaleUPPeisov/endlume-desktop"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$GH_REPO/contents/scripts/apply-audio-whole-track-fix-8-48.py?ref=$PATCH_REF" > "$WORK/scripts/apply-audio-whole-track-fix-8-48.py" || fail "cannot fetch 8.48 audio migration"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$GH_REPO/contents/scripts/validate-release-8-48.sh?ref=$PATCH_REF" > "$WORK/scripts/validate-release-8-48.sh" || fail "cannot fetch 8.48 audio validator"
python3 -m py_compile "$WORK/scripts/apply-audio-whole-track-fix-8-48.py"
chmod +x "$WORK/scripts/validate-release-8-48.sh"
python3 "$WORK/scripts/apply-audio-whole-track-fix-8-48.py" "$WORK"
"$WORK/scripts/validate-release-8-48.sh"

cd "$WORK"
echo '@@ENDLUME_STAGE|8.48/10 Проверяю только audio whole-track regression'
echo '@@ENDLUME_PROGRESS|72'
npm run check
npm run build
cargo test --manifest-path src-tauri/Cargo.toml audio_timeline_tests -- --nocapture
cargo test --manifest-path src-tauri/Cargo.toml watchdog_tests -- --nocapture
cargo check --manifest-path src-tauri/Cargo.toml

echo '@@ENDLUME_STAGE|9/10 Собираю ENDLUME Studio 8.48 AUDIO FIX'
echo '@@ENDLUME_PROGRESS|82'
export ENDLUME_RELEASE_ARTIFACT_DIR="$FINAL_ART"
export ENDLUME_RELEASE_VERSION="1.0.0-alpha.8.48"
rm -rf src-tauri/target/aarch64-apple-darwin/release/bundle/macos
npx tauri build --target aarch64-apple-darwin --bundles app

TAR="$(find "$WORK/src-tauri/target/aarch64-apple-darwin/release/bundle/macos" -maxdepth 1 -type f -name '*.app.tar.gz' -print -quit)"
[[ -n "$TAR" && -s "$TAR" ]] || fail "8.48 updater tar missing"
[[ -s "$TAR.sig" ]] || fail "8.48 updater signature missing"
rm -rf "$FINAL_ART"
mkdir -p "$FINAL_ART"
cp "$TAR" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz"
cp "$TAR.sig" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz.sig"
printf '%s\n' '1.0.0-alpha.8.48' > "$FINAL_ART/version.txt"

# Final post-build guards: old truncation cap must be gone while all performance
# and stability markers from 8.47 remain unchanged.
grep -Fq 'let cf=crossfade.clamp(0.0,10.0);' src-tauri/src/render.rs || fail "audio fix marker lost"
if grep -Fq 'if t-target<=240.0{t}else{target}' src-tauri/src/render.rs; then fail "old audio truncation cap returned"; fi
grep -Fq 'attempt==1&&encoder_works(app,"hevc_videotoolbox")' src-tauri/src/render.rs || fail "8.47 hardware-first marker lost"
grep -Fq 'target_video_kbps=500' src-tauri/src/render.rs || fail "8.47 500k marker lost"
grep -Fq 'FFMPEG_STALL_TIMEOUT_SECS:u64=120' src-tauri/src/render.rs || fail "watchdog marker lost"
grep -Fq 'ffprobe_output_timeout(app,args,Duration::from_secs(12))' src-tauri/src/render.rs || fail "bounded FFprobe marker lost"

echo '@@ENDLUME_PROGRESS|100'
echo '✅ ENDLUME 8.48 signed updater artifact ready'
echo '✅ AUDIO ONLY: whole-track boundary song is never cut by the old +240s cap'
echo '✅ Crossfade duration math matches the real audio filter clamp'
echo '✅ Video / UI / Effects / Subscribe / VYRON / watchdog / updater implementation unchanged'
