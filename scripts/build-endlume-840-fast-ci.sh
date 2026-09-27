#!/bin/bash
set -Eeuo pipefail
export COPYFILE_DISABLE=1
export COPY_EXTENDED_ATTRIBUTES_DISABLE=1
VERSION='1.0.0-alpha.8.40'
ASSET="${ENDLUME_CI_ASSET_NAME:-ENDLUME-Studio-${VERSION}-macos-arm64.zip}"
OUT="${ENDLUME_CI_ARTIFACT_DIR:-$PWD/release-out}"
fail(){ echo "❌ ENDLUME 8.40 FAST CI: $1" >&2; exit 1; }
[[ "$(uname -s)" == 'Darwin' && "$(uname -m)" == 'arm64' ]] || fail 'requires macOS arm64'
command -v node >/dev/null || fail 'node missing'
command -v npm >/dev/null || fail 'npm missing'
command -v cargo >/dev/null || fail 'cargo missing'
command -v ffmpeg >/dev/null || fail 'ffmpeg missing'
command -v ffprobe >/dev/null || fail 'ffprobe missing'

sanitize(){
  find . -path './.git' -prune -o -path './node_modules' -prune -o -path './src-tauri/target' -prune -o -type f -name '._*' -delete 2>/dev/null || true
}

sanitize
npm install --no-audit --no-fund
BIN_DIR='src-tauri/binaries'
rm -rf "$BIN_DIR" && mkdir -p "$BIN_DIR"
FFMPEG="$BIN_DIR/ffmpeg-aarch64-apple-darwin"
FFPROBE="$BIN_DIR/ffprobe-aarch64-apple-darwin"
install -m 755 "$(command -v ffmpeg)" "$FFMPEG"
install -m 755 "$(command -v ffprobe)" "$FFPROBE"
"$FFMPEG" -hide_banner -encoders > /tmp/endlume-840-encoders.txt
"$FFMPEG" -hide_banner -protocols > /tmp/endlume-840-protocols.txt
grep -q libx265 /tmp/endlume-840-encoders.txt || fail 'ffmpeg libx265 missing'
grep -q hevc_videotoolbox /tmp/endlume-840-encoders.txt || fail 'ffmpeg hevc_videotoolbox missing'
grep -q alac /tmp/endlume-840-encoders.txt || fail 'ffmpeg ALAC missing'
grep -q concatf /tmp/endlume-840-protocols.txt || fail 'ffmpeg concatf missing'

python3 -m py_compile \
 scripts/apply-render-stability-8-25.py scripts/apply-release-ui-8-25.py \
 scripts/apply-smart-repeat-8-26.py scripts/apply-ui-version-8-26.py \
 scripts/apply-original-fidelity-8-27.py scripts/apply-original-fidelity-ui-8-27.py \
 scripts/apply-hybrid-fidelity-8-28.py scripts/apply-hybrid-fidelity-ui-8-28.py \
 scripts/repair-hybrid-patcher-8-29.py scripts/apply-version-8-30.py \
 scripts/apply-runtime-ux-8-31.py scripts/apply-version-8-31.py \
 scripts/repair-updater-replay-8-32.py scripts/apply-queue-updater-8-32.py scripts/apply-version-8-32.py \
 scripts/repair-speed-workdir-8-33.py scripts/apply-speed-fidelity-8-33.py scripts/apply-version-8-33.py \
 scripts/apply-stability-8-34.py scripts/apply-version-8-34.py \
 scripts/apply-strict-fidelity-8-35.py scripts/apply-version-8-35.py scripts/repair-strict-store-8-35.py \
 scripts/apply-fidelity-1080p-8-36.py scripts/apply-version-8-36.py \
 scripts/repair-settings-updater-8-37.py scripts/apply-remote-updater-8-37.py scripts/apply-version-8-37.py \
 scripts/apply-youtube-fill-8-38.py scripts/apply-version-8-38.py \
 scripts/apply-performance-fidelity-8-39.py scripts/apply-hybrid-updater-8-39.py scripts/apply-version-8-39.py \
 scripts/apply-vyron-bridge-8-40.py

python3 scripts/repair-hybrid-patcher-8-29.py
python3 -m py_compile scripts/apply-hybrid-fidelity-8-28.py
python3 scripts/apply-render-stability-8-25.py
python3 scripts/apply-release-ui-8-25.py
python3 scripts/apply-smart-repeat-8-26.py
python3 scripts/apply-ui-version-8-26.py
python3 scripts/apply-original-fidelity-8-27.py
python3 scripts/apply-original-fidelity-ui-8-27.py
python3 scripts/apply-hybrid-fidelity-8-28.py
python3 scripts/apply-hybrid-fidelity-ui-8-28.py
python3 scripts/apply-version-8-30.py
python3 scripts/apply-runtime-ux-8-31.py
python3 scripts/apply-version-8-31.py
python3 scripts/repair-updater-replay-8-32.py
python3 scripts/apply-queue-updater-8-32.py
python3 scripts/apply-version-8-32.py
chmod +x scripts/validate-release-8-32.sh
scripts/validate-release-8-32.sh
python3 scripts/repair-speed-workdir-8-33.py
python3 scripts/apply-speed-fidelity-8-33.py
python3 scripts/apply-version-8-33.py
python3 scripts/apply-stability-8-34.py
python3 scripts/apply-version-8-34.py
python3 scripts/apply-strict-fidelity-8-35.py
python3 scripts/apply-version-8-35.py
python3 scripts/repair-strict-store-8-35.py
chmod +x scripts/validate-release-8-33.sh scripts/validate-release-8-34.sh
scripts/validate-release-8-33.sh "$FFMPEG" "$FFPROBE"
scripts/validate-release-8-34.sh "$FFMPEG" "$FFPROBE"
python3 scripts/apply-fidelity-1080p-8-36.py
python3 scripts/apply-version-8-36.py
chmod +x scripts/validate-release-8-36.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
python3 scripts/repair-settings-updater-8-37.py
python3 scripts/apply-remote-updater-8-37.py
python3 scripts/apply-version-8-37.py
chmod +x scripts/validate-release-8-37.sh
scripts/validate-release-8-37.sh
python3 scripts/apply-youtube-fill-8-38.py
python3 scripts/apply-version-8-38.py
chmod +x scripts/validate-release-8-38.sh
scripts/validate-release-8-38.sh "$FFMPEG" "$FFPROBE"

# Replay compatibility: 8.25 intentionally converted the render keyer to RGB colorkey,
# while the original 8.39 patch expected the older chromakey expression. Preserve
# colorkey and add the same despill stage before applying the rest of 8.39.
python3 - <<'PY'
from pathlib import Path
p=Path('src-tauri/src/render.rs')
r=p.read_text(encoding='utf-8')
marker='despill=type={}:mix={}:expand=0.20'
if marker not in r:
    old='format!("[{idx}:v]fps={},format=rgba,colorkey={}:{}:{}",s.fps,color_ffmpeg(&e.key_color),e.similarity.clamp(0.001,0.60),e.blend.clamp(0.001,0.35))'
    new='format!("[{idx}:v]fps={},format=rgba,colorkey={}:{}:{},despill=type={}:mix={}:expand=0.20",s.fps,color_ffmpeg(&e.key_color),e.similarity.clamp(0.001,0.60),e.blend.clamp(0.001,0.35),chroma_despill_type(&e.key_color),e.despill.clamp(0.0,1.0))'
    if old not in r:
        raise SystemExit('8.40 replay repair: colorkey render marker missing')
    r=r.replace(old,new,1)
    p.write_text(r,encoding='utf-8')
print('8.40 replay repair: colorkey + despill compatibility ready')
PY

python3 scripts/apply-performance-fidelity-8-39.py
python3 scripts/apply-hybrid-updater-8-39.py
python3 scripts/apply-version-8-39.py
chmod +x scripts/validate-release-8-39.sh
scripts/validate-release-8-39.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs

python3 scripts/apply-vyron-bridge-8-40.py
npm run check
npm run build
cargo test --manifest-path src-tauri/Cargo.toml --lib -- --nocapture
cargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin

grep -Fq 'mod vyron_bridge;' src-tauri/src/lib.rs || fail 'native bridge module missing'
grep -Fq 'vyron_bridge::consume_vyron_batch_request' src-tauri/src/lib.rs || fail 'native bridge commands missing'
grep -Fq 'consumeVyronBatch:' src/tauri.ts || fail 'frontend bridge API missing'
grep -Fq '<VyronBatchBridge/>' src/pages/App.tsx || fail 'frontend bridge mount missing'
grep -Fq 'onClick={enqueue}' src/pages/ProjectPage.tsx || fail 'legacy enqueue handler missing'
grep -Fq "openEditor({kind:'subscribe'})" src/pages/ProjectPage.tsx || fail 'legacy subscribe handler missing'
grep -Fq "openEditor({kind:'effects'})" src/pages/ProjectPage.tsx || fail 'legacy effects handler missing'
grep -Eq '"version": "1\.0\.0-alpha\.8\.40"' package.json || fail 'package version is not 8.40'

sanitize
npx tauri build --target aarch64-apple-darwin --bundles app --config src-tauri/tauri.local.conf.json
APP='src-tauri/target/aarch64-apple-darwin/release/bundle/macos/ENDLUME Studio.app'
[[ -d "$APP" ]] || fail 'Tauri app missing'
[[ "$(plutil -extract CFBundleIdentifier raw -o - "$APP/Contents/Info.plist")" == 'studio.endlume.desktop' ]] || fail 'bundle id mismatch'
[[ "$(plutil -extract CFBundleShortVersionString raw -o - "$APP/Contents/Info.plist")" == "$VERSION" ]] || fail 'bundle version mismatch'
find "$APP/Contents/MacOS" -maxdepth 1 -type f \( -name 'ffmpeg*' -o -name 'ffprobe*' \) -exec chmod 755 {} +
BFF="$(find "$APP/Contents/MacOS" -maxdepth 1 -type f -name 'ffmpeg*' -print -quit)"
BFP="$(find "$APP/Contents/MacOS" -maxdepth 1 -type f -name 'ffprobe*' -print -quit)"
[[ -x "$BFF" && -x "$BFP" ]] || fail 'bundled ffmpeg/ffprobe missing'
codesign --force --deep --sign - "$APP" >/dev/null
codesign --verify --deep --strict "$APP"

SMOKE="$(mktemp -d)"
"$BFF" -hide_banner -loglevel error -f lavfi -i 'color=c=0x182038:size=1920x1080:rate=60' -t 1 -an -c:v hevc_videotoolbox -realtime 1 -b:v 600k -tag:v hvc1 -pix_fmt yuv420p -y "$SMOKE/v.mp4"
"$BFF" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=44100' -t 1 -ac 2 -c:a libmp3lame -b:a 320k -y "$SMOKE/a.mp3"
"$BFF" -hide_banner -loglevel error -i "$SMOKE/v.mp4" -i "$SMOKE/a.mp3" -map 0:v:0 -map 1:a:0 -c copy -y "$SMOKE/final.mov"
"$BFP" -v error -show_entries stream=codec_type -of csv=p=0 "$SMOKE/final.mov" | grep -q video || fail 'final smoke video stream missing'
"$BFP" -v error -show_entries stream=codec_type -of csv=p=0 "$SMOKE/final.mov" | grep -q audio || fail 'final smoke audio stream missing'
rm -rf "$SMOKE"

rm -rf "$OUT" && mkdir -p "$OUT"
/usr/bin/ditto -c -k --keepParent "$APP" "$OUT/$ASSET"
(cd "$OUT" && shasum -a 256 "$ASSET" > "$ASSET.sha256")
[[ -s "$OUT/$ASSET" && -s "$OUT/$ASSET.sha256" ]] || fail 'release package missing'
echo '✅ ENDLUME 8.40 FAST CI BUILD PASS'
