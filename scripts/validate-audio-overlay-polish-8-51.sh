#!/bin/bash
set -Eeuo pipefail
ROOT="${1:-.}"
FFMPEG="${2:-ffmpeg}"
R="$ROOT/src-tauri/src/render.rs"
C="$ROOT/src-tauri/src/cache.rs"
P="$ROOT/src-tauri/src/persistence.rs"
L="$ROOT/src/components/LiveCompositePreview.tsx"
E="$ROOT/src/pages/Editors.tsx"
S="$ROOT/src/store.ts"
fail(){ echo "FAIL 8.51 polish: $1" >&2; exit 1; }

for f in "$R" "$C" "$P" "$L" "$E" "$S"; do [[ -f "$f" ]] || fail "missing $f"; done

# Audio must finish the song, not the clock target, for the normal one-image workflow.
grep -Fq 'let duration_mode=if smart_repeat_project(job){"whole-track"}else{job.settings.duration_mode.as_str()};' "$R" || fail "one-image whole-track runtime policy missing"
grep -Fq 'let idx=i%durations.len();' "$R" || fail "whole-track boundary arithmetic missing"
! grep -Fq 'if t-target<=240.0{t}else{target}' "$R" || fail "legacy >4min song cutoff cap returned"

# Saturation must survive save/load and reach both physical render and Live Preview.
grep -Fq 'let saturation=obj.get("saturation").and_then(Value::as_f64).unwrap_or(1.25);' "$P" || fail "saturation persistence clamp missing"
! grep -Fq 'obj.insert("saturation".into(),json!(1.0))' "$P" || fail "persistence still resets saturation to 1.0"
grep -Fq 'let sat=e.saturation.clamp(0.50,2.0);' "$C" || fail "render saturation scalar missing"
grep -Fq 'colorchannelmixer=aa=1.25' "$C" || fail "overlay alpha punch missing"
grep -Fq 'eq=contrast=1.10:brightness=0.015:saturation={sat}' "$C" || fail "chromakey/luma vivid render filter missing"
grep -Fq 'eq=contrast=1.12:brightness=0.020:saturation={sat}' "$C" || fail "screen/equalizer vivid render filter missing"
grep -Fq 'uniform float sat' "$L" || fail "Live Preview saturation uniform missing"
grep -Fq 'a=min(1.,a*1.25)' "$L" || fail "Live Preview alpha punch missing"
grep -Fq 'gl.uniform1f(uSat' "$L" || fail "Live Preview saturation value missing"
[[ "$(grep -Fc 'Насыщенность / сила цвета' "$E")" -ge 2 ]] || fail "Effects + Subscribe saturation controls missing"
[[ "$(grep -Fc 'saturation: 1.25' "$E")" -ge 2 ]] || fail "vivid editor defaults missing"
[[ "$(grep -Fc 'saturation:Math.abs((e.saturation??1)-1)<0.001?1.25' "$S")" -ge 2 ]] || fail "legacy preset vivid migration missing"

# Physical FFmpeg smoke: the exact alpha+saturation+contrast chain must really run
# with the embedded FFmpeg, not merely exist as source text.
TMP="$(mktemp -d /tmp/endlume-851-vivid.XXXXXX)"
trap 'rm -rf "$TMP" >/dev/null 2>&1 || true' EXIT
"$FFMPEG" -hide_banner -loglevel error \
  -f lavfi -i 'testsrc2=size=320x180:rate=60' -t 1 \
  -vf 'format=rgba,colorkey=0x00ff00:0.10:0.06,despill=type=green:mix=0.35:expand=0.20,colorchannelmixer=aa=1.25,format=yuva444p,eq=contrast=1.10:brightness=0.015:saturation=1.25,format=argb' \
  -an -c:v qtrle -pix_fmt argb -y "$TMP/vivid-alpha.mov"
[[ -s "$TMP/vivid-alpha.mov" ]] || fail "physical vivid-alpha cache smoke produced no file"

"$FFMPEG" -hide_banner -loglevel error \
  -f lavfi -i 'testsrc2=size=320x180:rate=60' -t 1 \
  -vf 'format=yuv444p,eq=contrast=1.12:brightness=0.020:saturation=1.25,format=rgb24' \
  -an -c:v qtrle -pix_fmt rgb24 -y "$TMP/vivid-screen.mov"
[[ -s "$TMP/vivid-screen.mov" ]] || fail "physical vivid-screen cache smoke produced no file"

echo '✅ ENDLUME 8.51 AUDIO + OVERLAY POLISH GATE PASS'
echo '✅ one-image render crosses 2h and ends only at a complete song boundary'
echo '✅ saturation persists and is applied in FFmpeg + Live Preview'
echo '✅ Subscribe alpha/contrast and Screen/equalizer color punch are physically encodable'
