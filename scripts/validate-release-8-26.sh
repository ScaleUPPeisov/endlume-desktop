#!/bin/bash
set -euo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"

# Keep every 8.25 gate: Loop Mode 100/100, Effects, Subscribe, audio and mux.
scripts/validate-release-8-25.sh "$FFMPEG" "$FFPROBE"

assert_contains(){ local needle="$1" file="$2" label="$3"; grep -Fq "$needle" "$file" || { echo "FAIL: $label"; echo "Expected: $needle"; exit 1; }; echo "PASS: $label"; }

assert_contains 'fn smart_repeat_project(' src-tauri/src/render.rs 'Smart Repeat project detection'
assert_contains 'if is_image(media) && total==1{' src-tauri/src/render.rs 'still image keeps Smart Size with overlays'
assert_contains 'encoder_args(encoder,&job.settings,smart)' src-tauri/src/render.rs 'Effect variant uses Smart Size bitrate'
assert_contains 'let visual_master_duration=if smart_repeat' src-tauri/src/render.rs 'Effect loop duration participates in visual master'
assert_contains '"smartRepeat":smart_repeat' src-tauri/src/render.rs 'Render Center receives Smart Repeat profile'
assert_contains '0..=1920=>520' src-tauri/src/render.rs '1080p Smart Repeat bitrate budget'
assert_contains '1921..=2560=>600' src-tauri/src/render.rs '1440p Smart Repeat bitrate budget'
assert_contains '_=>700' src-tauri/src/render.rs '4K Smart Repeat bitrate budget'
assert_contains 'job.project.media[0].as_str()' src-tauri/src/render.rs 'Effects variant starts from original image'

# Hard size budget math for a 2h file with AAC 320k.
python3 - <<'PY'
for name,video_kbps in [('1080p',520),('1440p',600),('4K',700)]:
    total_kbps=video_kbps+320
    mb=total_kbps*7200/8/1000
    if not 700 <= mb <= 1000:
        raise SystemExit(f'FAIL: {name} 2h target {mb:.1f} MB is outside 700–1000 MB')
    print(f'PASS: {name} 2h projected size ≈ {mb:.0f} MB before small container overhead')
PY

# A short real encode verifies that a moving overlay can be encoded using the
# same low-average/high-peak concept without changing aspect ratio.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
BASE="$TMP/base.png"
FX="$TMP/fx.mov"
OUT="$TMP/smart-repeat.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x203048:size=640x360' -frames:v 1 -y "$BASE"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=black@0.0:size=180x180:rate=30,format=rgba,drawbox=x=35:y=35:w=110:h=110:color=0xff3355:t=fill' -t 2 -an -c:v qtrle -pix_fmt argb -y "$FX"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$BASE" -stream_loop -1 -i "$FX" -filter_complex "[0:v]scale=640:360,fps=30,setsar=1[b];[1:v]scale=220:-2:flags=lanczos[f];[b][f]overlay=x='max(0,min(W-w,W*0.5-w/2))':y='max(0,min(H-h,H*0.5-h/2))':shortest=1:eof_action=repeat[outv]" -map '[outv]' -t 4 -an -c:v libx264 -preset veryfast -b:v 700k -maxrate 6000k -bufsize 12000k -g 360 -keyint_min 360 -sc_threshold 0 -pix_fmt yuv420p -y "$OUT"
"$FFPROBE" -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$OUT" | grep -q '^640x360$'
test -s "$OUT"
echo 'PASS: Smart Repeat moving-overlay encode is valid and aspect-safe'

echo 'ENDLUME 8.26 Smart Repeat regression gate passed.'
