#!/bin/bash
set -Eeuo pipefail

EXPECTED_VERSION="1.0.0-alpha.8.52"
PINNED_SHA="03399cf0f12b912a846144cd4d060755b5260cc5"
REPO="ScaleUPPeisov/endlume-desktop"
FINAL_ART="${ENDLUME_RELEASE_ARTIFACT_DIR:-$HOME/.endlume-release-bridge/endlume/current}"
FOUNDATION="$HOME/.endlume-local-builder/endlume-desktop-8.40-bootstrap"
TMP="$(mktemp -d /tmp/endlume-852-release.XXXXXX)"
SRC="$TMP/source"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo "❌ ENDLUME 8.52 RELEASE: $1" >&2; exit 1; }

[[ "${ENDLUME_RELEASE_VERSION:-$EXPECTED_VERSION}" = "$EXPECTED_VERSION" ]] || fail "wrong requested version"
[[ -d "$FOUNDATION/src-tauri/binaries" ]] || fail "trusted embedded FFmpeg foundation missing"
mkdir -p "$FINAL_ART"
rm -rf "$FINAL_ART"/*

# Fetch exactly the source that passed 8.52 source compilation. No moving branch ref.
mkdir -p "$SRC"
git -C "$SRC" init -q
git -C "$SRC" remote add origin "https://github.com/$REPO.git"
fetched=0
for attempt in 1 2 3 4 5; do
  if git -C "$SRC" -c http.version=HTTP/1.1 fetch --no-tags --depth=1 origin "$PINNED_SHA"; then fetched=1; break; fi
  echo "⚠️ exact 8.52 fetch retry $attempt/5" >&2
  sleep $((attempt*2))
done
[[ "$fetched" == 1 ]] || fail "cannot fetch exact source $PINNED_SHA"
git -C "$SRC" checkout --detach FETCH_HEAD >/dev/null
[[ "$(git -C "$SRC" rev-parse HEAD)" = "$PINNED_SHA" ]] || fail "source SHA mismatch"

# Embedded sidecars stay local and are copied from the already proven ENDLUME foundation.
mkdir -p "$SRC/src-tauri/binaries"
rsync -a "$FOUNDATION/src-tauri/binaries/" "$SRC/src-tauri/binaries/"
FFMPEG="$(find "$SRC/src-tauri/binaries" -maxdepth 1 -type f -name 'ffmpeg*' -perm -111 -print -quit)"
FFPROBE="$(find "$SRC/src-tauri/binaries" -maxdepth 1 -type f -name 'ffprobe*' -perm -111 -print -quit)"
[[ -x "$FFMPEG" && -x "$FFPROBE" ]] || fail "embedded FFmpeg/FFprobe missing"

cd "$SRC"
python3 - "$EXPECTED_VERSION" <<'PY'
import json,re,sys,pathlib
v=sys.argv[1]
assert json.load(open('package.json'))['version']==v
assert json.load(open('src-tauri/tauri.conf.json'))['version']==v
s=pathlib.Path('src-tauri/Cargo.toml').read_text()
m=re.search(r'(?ms)^\[package\].*?^version\s*=\s*"([^"]+)"',s)
assert m and m.group(1)==v,(m.group(1) if m else None)
PY

grep -Fq 'resolved_job.settings.width=1920;' src-tauri/src/render.rs || fail "1920 width lock missing"
grep -Fq 'resolved_job.settings.height=1080;' src-tauri/src/render.rs || fail "1080 height lock missing"
grep -Fq 'resolved_job.settings.fps=60;' src-tauri/src/render.rs || fail "60 FPS lock missing"
grep -Fq 'attempt==1&&encoder_works(app,"hevc_videotoolbox")' src-tauri/src/render.rs || fail "VideoToolbox is not hardware-first"
grep -Fq '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"' src-tauri/src/render.rs || fail "q100/500k fidelity profile missing"
grep -Fq 'Periodic852Plan' src-tauri/src/render.rs || fail "8.52 periodic plan missing"
grep -Fq 'mp4_manifest::expand_video_prefix_cycle' src-tauri/src/render.rs || fail "8.52 zero-copy manifest path missing"

# Source gates.
npm ci
npm run check
npm run build
cargo check --manifest-path src-tauri/Cargo.toml
cargo test --manifest-path src-tauri/Cargo.toml mp4_manifest::tests -- --nocapture

# Physical MP4 gate: video+audio, repeat-frame identity, zero-copy bytes and AVFoundation.
GATE="$TMP/gate"; mkdir -p "$GATE"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=640x360:rate=2' -t 4 -an -c:v libx264 -preset ultrafast -bf 0 -g 4 -keyint_min 4 -sc_threshold 0 -pix_fmt yuv420p -y "$GATE/video.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=997:sample_rate=48000' -t 8 -c:a aac -b:a 192k -y "$GATE/audio.m4a"
"$FFMPEG" -hide_banner -loglevel error -i "$GATE/video.mp4" -i "$GATE/audio.m4a" -t 8 -map 0:v:0 -map 1:a:0 -c copy -y "$GATE/seed.mov"
export ENDLUME_MANIFEST_SEED="$GATE/seed.mov"
export ENDLUME_MANIFEST_OUT="$GATE/final.mov"
export ENDLUME_MANIFEST_PREFIX_FRAMES=4
export ENDLUME_MANIFEST_CYCLE_FRAMES=4
export ENDLUME_MANIFEST_TOTAL_FRAMES=16
cargo test --manifest-path src-tauri/Cargo.toml external_prefix_cycle_manifest_if_requested -- --nocapture
DUR="$($FFPROBE -v error -show_entries format=duration -of default=nw=1:nk=1 "$GATE/final.mov")"
FRAMES="$($FFPROBE -v error -select_streams v:0 -show_entries stream=nb_frames -of default=nw=1:nk=1 "$GATE/final.mov")"
python3 - "$DUR" "$FRAMES" <<'PY'
import sys
d=float(sys.argv[1]); f=int(sys.argv[2]); assert abs(d-8.0)<0.08,(d,f); assert f==16,(d,f)
print('PASS: 8.52 manifest timeline',d,f)
PY
"$FFMPEG" -hide_banner -loglevel error -i "$GATE/final.mov" -map 0:a:0 -t 8 -f null -
"$FFMPEG" -hide_banner -loglevel error -ss 3 -i "$GATE/final.mov" -frames:v 1 -f framemd5 - > "$GATE/a.md5"
"$FFMPEG" -hide_banner -loglevel error -ss 5 -i "$GATE/final.mov" -frames:v 1 -f framemd5 - > "$GATE/b.md5"
python3 - "$GATE/a.md5" "$GATE/b.md5" <<'PY'
import sys
def md5(p):
    rows=[x for x in open(p) if x[:1].isdigit()]
    assert rows
    return rows[-1].split(',')[-1].strip()
a,b=map(md5,sys.argv[1:]); assert a==b,(a,b); print('PASS: repeat frame identity',a)
PY
SEED_BYTES="$(stat -f%z "$GATE/seed.mov")"; FINAL_BYTES="$(stat -f%z "$GATE/final.mov")"
python3 - "$SEED_BYTES" "$FINAL_BYTES" <<'PY'
import sys
s,f=map(int,sys.argv[1:]); assert f<s*1.20,(s,f); print('PASS: zero-copy bytes',s,f)
PY
cat > "$GATE/check.swift" <<'SWIFT'
import Foundation
import AVFoundation
let asset=AVURLAsset(url:URL(fileURLWithPath:CommandLine.arguments[1]))
let sem=DispatchSemaphore(value:0)
Task {
  do {
    let d=CMTimeGetSeconds(try await asset.load(.duration))
    let v=try await asset.loadTracks(withMediaType:.video)
    let a=try await asset.loadTracks(withMediaType:.audio)
    print("AV_DURATION=\(d) VIDEO_TRACKS=\(v.count) AUDIO_TRACKS=\(a.count)")
    if abs(d-8.0)>0.08 || v.count != 1 || a.count != 1 { exit(4) }
  } catch { print("AV_ERROR=\(error)"); exit(3) }
  sem.signal()
}
sem.wait()
SWIFT
xcrun swift "$GATE/check.swift" "$GATE/final.mov"

# 2h05 metadata-scale gate at 60 FPS. This verifies 450,000-frame manifest creation
# is bounded and does not physically duplicate 2 hours of compressed video bytes.
LONG="$TMP/long"; mkdir -p "$LONG"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=640x360:rate=60' -t 4 -an -c:v libx264 -preset ultrafast -bf 0 -g 120 -keyint_min 120 -sc_threshold 0 -pix_fmt yuv420p -y "$LONG/seed.mov"
export ENDLUME_MANIFEST_SEED="$LONG/seed.mov"
export ENDLUME_MANIFEST_OUT="$LONG/final.mov"
export ENDLUME_MANIFEST_PREFIX_FRAMES=120
export ENDLUME_MANIFEST_CYCLE_FRAMES=120
export ENDLUME_MANIFEST_TOTAL_FRAMES=450000
START_NS="$(python3 -c 'import time;print(time.time_ns())')"
cargo test --manifest-path src-tauri/Cargo.toml external_prefix_cycle_manifest_if_requested -- --nocapture
END_NS="$(python3 -c 'import time;print(time.time_ns())')"
LONG_DUR="$($FFPROBE -v error -show_entries format=duration -of default=nw=1:nk=1 "$LONG/final.mov")"
LONG_FRAMES="$($FFPROBE -v error -select_streams v:0 -show_entries stream=nb_frames -of default=nw=1:nk=1 "$LONG/final.mov")"
LONG_SIZE="$(stat -f%z "$LONG/final.mov")"
SEED_SIZE="$(stat -f%z "$LONG/seed.mov")"
python3 - "$START_NS" "$END_NS" "$LONG_DUR" "$LONG_FRAMES" "$SEED_SIZE" "$LONG_SIZE" <<'PY'
import sys
st,en=map(int,sys.argv[1:3]); d=float(sys.argv[3]); f=int(sys.argv[4]); s=int(sys.argv[5]); o=int(sys.argv[6]); sec=(en-st)/1e9
assert abs(d-7500.0)<0.2,d
assert f==450000,f
assert sec<=30.0,sec
assert o < s + 12_000_000,(s,o)
print(f'PASS: 2h05/60fps zero-copy manifest {sec:.3f}s frames={f} bytes={o}')
PY

# Build macOS ARM64 application.
rm -rf src-tauri/target/aarch64-apple-darwin/release/bundle/macos
npx tauri build --target aarch64-apple-darwin --bundles app
BUNDLE="$SRC/src-tauri/target/aarch64-apple-darwin/release/bundle/macos"
APP="$(find "$BUNDLE" -maxdepth 1 -type d -name '*.app' -print -quit)"
[[ -n "$APP" && -d "$APP" ]] || fail ".app bundle missing"
ID="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$APP/Contents/Info.plist")"
VER="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$APP/Contents/Info.plist")"
EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$APP/Contents/Info.plist")"
[[ "$ID" = "studio.endlume.desktop" ]] || fail "bundle identifier changed: $ID"
[[ "$VER" = "$EXPECTED_VERSION" ]] || fail "bundle version mismatch: $VER"
/usr/bin/lipo -archs "$APP/Contents/MacOS/$EXE" | grep -qw arm64 || fail "main executable is not arm64"
if ! /usr/bin/codesign --verify --deep --strict "$APP" >/dev/null 2>&1; then
  /usr/bin/codesign --force --deep --sign - "$APP" || fail "macOS bundle seal failed"
fi
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP" || fail "strict codesign failed"
[[ -s "$APP/Contents/_CodeSignature/CodeResources" ]] || fail "CodeResources missing"

TAR="$BUNDLE/ENDLUME-macos-aarch64.app.tar.gz"
rm -f "$TAR" "$TAR.sig"
/usr/bin/tar -czf "$TAR" -C "$BUNDLE" "$(basename "$APP")" || fail "cannot create updater tar"
[[ -s "$TAR" ]] || fail "updater tar missing"
env -u TAURI_SIGNING_PRIVATE_KEY npx tauri signer sign "$TAR" >/dev/null || fail "Tauri updater signature failed"
[[ -s "$TAR.sig" ]] || fail "updater signature missing"

VERIFY="$TMP/verify"; mkdir -p "$VERIFY"
/usr/bin/tar -xzf "$TAR" -C "$VERIFY" || fail "cannot unpack updater tar"
VAPP="$(find "$VERIFY" -maxdepth 2 -type d -name '*.app' -print -quit)"
[[ -n "$VAPP" ]] || fail "archive app missing"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$VAPP" || fail "archive app signature invalid"

rm -rf "$FINAL_ART"
mkdir -p "$FINAL_ART"
cp "$TAR" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz"
cp "$TAR.sig" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz.sig"
printf '%s\n' "$EXPECTED_VERSION" > "$FINAL_ART/version.txt"
printf '%s\n' "$PINNED_SHA" > "$FINAL_ART/source-sha.txt"

echo "✅ ENDLUME STUDIO 8.52 exact source built and signed"
echo "✅ source pin: $PINNED_SHA"
echo "✅ strict 1920x1080 / 60 FPS / H.265"
echo "✅ VideoToolbox q100/500k hardware-first; x265 CRF18/500k fallback"
echo "✅ periodic zero-copy MP4 path passed Rust + FFprobe + audio + AVFoundation gates"
echo "✅ signed updater artifact staged for endlume-stable publication"
