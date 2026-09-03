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

SIGNING_KEY_PATH="${TAURI_SIGNING_PRIVATE_KEY_PATH:-$HOME/.endlume-updater/endlume.key}"
[[ -s "$SIGNING_KEY_PATH" ]] || fail "Tauri updater private key file missing"
export TAURI_SIGNING_PRIVATE_KEY_PATH="$SIGNING_KEY_PATH"
export TAURI_SIGNING_PRIVATE_KEY="$(cat "$SIGNING_KEY_PATH")"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:-}"

# Exact stable 8.50 foundation.
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

echo "✅ 8.50 reconstructed; applying 8.51 SPEED + WHOLE-SONG + VIVID OVERLAYS + 500-700MB PROFILE from ref=$PATCH_REF"
mkdir -p "$WORK/scripts"
GH_REPO="ScaleUPPeisov/endlume-desktop"
for f in apply-full-project-speed-8-51.py apply-audio-overlay-polish-8-51.py apply-size-fidelity-8-51.py validate-release-8-51.sh validate-audio-overlay-polish-8-51.sh; do
  gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$GH_REPO/contents/scripts/$f?ref=$PATCH_REF" > "$WORK/scripts/$f" || fail "cannot fetch $f"
done

# Exact 8.50 is reconstructed by a migration chain, so formatting around the
# visual planner may differ while semantics stay identical. Harden only the
# migration's function locator; this does not alter runtime behavior.
python3 - "$WORK/scripts/apply-full-project-speed-8-51.py" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text(encoding='utf-8')
old="""start=s.find('async fn assemble_visual(')\nend=s.find('\\n\\nasync fn ',start+10)\nmust(start>=0 and end>start,'assemble_visual block not found')"""
new="""m=re.search(r'(?m)^(?:pub\\s+)?async\\s+fn\\s+assemble_visual\\s*\\(',s)\nif m:\n    start=m.start()\nelse:\n    marker=s.find('\\\"Склеиваю визуальную дорожку\\\"')\n    if marker<0: marker=s.find('VisualSource::Concat(list)')\n    starts=[x.start() for x in re.finditer(r'(?m)^(?:pub\\s+)?async\\s+fn\\s+\\w+\\s*\\(',s) if marker>=0 and x.start()<marker]\n    start=starts[-1] if starts else -1\nnexts=[x.start() for x in re.finditer(r'(?m)^(?:pub\\s+)?async\\s+fn\\s+\\w+\\s*\\(',s) if start>=0 and x.start()>start]\nend=nexts[0] if nexts else -1\nmust(start>=0 and end>start,'assemble_visual block not found')"""
if old not in s:
    raise SystemExit('8.51 builder: visual matcher patch anchor missing')
p.write_text(s.replace(old,new,1),encoding='utf-8')
PY

python3 -m py_compile "$WORK/scripts/apply-full-project-speed-8-51.py" "$WORK/scripts/apply-audio-overlay-polish-8-51.py" "$WORK/scripts/apply-size-fidelity-8-51.py"
/bin/bash -n "$WORK/scripts/validate-release-8-51.sh"
/bin/bash -n "$WORK/scripts/validate-audio-overlay-polish-8-51.sh"
chmod +x "$WORK/scripts/validate-release-8-51.sh" "$WORK/scripts/validate-audio-overlay-polish-8-51.sh"

python3 "$WORK/scripts/apply-full-project-speed-8-51.py" "$WORK"
python3 "$WORK/scripts/apply-audio-overlay-polish-8-51.py" "$WORK"
python3 "$WORK/scripts/apply-size-fidelity-8-51.py" "$WORK"
"$WORK/scripts/validate-release-8-51.sh" "$WORK" "$FFMPEG" "$FFPROBE"
"$WORK/scripts/validate-audio-overlay-polish-8-51.sh" "$WORK" "$FFMPEG"

cd "$WORK"
echo '@@ENDLUME_STAGE|8.51/10 Проверяю 20–30s / 500–700MB / whole-song / vivid overlays'
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
grep -Fq '"-b:v","400k","-maxrate","12M","-bufsize","64M"' src-tauri/src/render.rs || fail "400k compact fidelity profile lost"
grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{400}' src-tauri/src/render.rs || fail "400k budget lost"
if grep -Fq '"-q:v","100"' src-tauri/src/render.rs; then fail "q100 size bypass returned"; fi
grep -Fq 'let idx=i%durations.len();' src-tauri/src/render.rs || fail "whole-track math lost"
grep -Fq 'let duration_mode=if smart_repeat_project(job){"whole-track"}else{job.settings.duration_mode.as_str()};' src-tauri/src/render.rs || fail "one-image whole-song policy lost"
grep -Fq 'eq=contrast=1.10:brightness=0.015:saturation={sat}' src-tauri/src/cache.rs || fail "vivid overlay render path lost"
grep -Fq 'uniform float sat' src/components/LiveCompositePreview.tsx || fail "vivid Live Preview path lost"
if grep -Fq 'if t-target<=240.0{t}else{target}' src-tauri/src/render.rs; then fail "song cut cap returned"; fi

echo '@@ENDLUME_PROGRESS|100'
echo '✅ ENDLUME STUDIO PEISOV 8.51 candidate ready'
echo '✅ full-project manifest-only assembly; no duplicate multi-minute normal visual files'
echo '✅ physical 2h05 test is 500–700 MB while keeping HQ320 audio pressure'
echo '✅ one-image videos finish the current song after 2h; no abrupt music cutoff'
echo '✅ Subscribe/equalizer vivid pipeline is preserved in Preview and final render'
echo '✅ VideoToolbox 400k compact profile / 1920x1080 / watchdog / updater identity preserved'
echo '✅ signed updater archive contains strict-valid ENDLUME STUDIO PEISOV.app'
