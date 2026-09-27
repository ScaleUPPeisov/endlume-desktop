#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
R="$ROOT/src-tauri/src/render.rs"
fail(){ echo "FAIL 8.47: $1" >&2; exit 1; }
[[ -f "$R" ]] || fail "render.rs missing"
grep -Fq 'attempt==1&&encoder_works(app,"hevc_videotoolbox")' "$R" || fail 'VideoToolbox is not first choice'
grep -Fq '"-prio_speed","1"' "$R" || fail 'VideoToolbox speed priority missing'
grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' "$R" || fail '500k budget changed'
grep -Fq 'resolved_job.settings.width=1920;' "$R" || fail '1920 width lock changed'
grep -Fq 'resolved_job.settings.height=1080;' "$R" || fail '1080 height lock changed'
grep -Fq 'ffprobe_output_timeout(app,args,Duration::from_secs(12))' "$R" || fail 'bounded final FFprobe lost'
grep -Fq 'FFMPEG_STALL_TIMEOUT_SECS:u64=120' "$R" || fail 'watchdog lost'
grep -Fq 'target_video_kbps=500' "$R" || fail 'performance diagnostics missing'
python3 - "$R" <<'PY'
import sys
s=open(sys.argv[1],encoding='utf-8').read()
line=[x for x in s.splitlines() if '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"' in x]
assert line, 'final mux line missing'
assert all('+faststart' not in x for x in line), 'final mux still has +faststart'
a=s.index('attempt==1&&encoder_works(app,"hevc_videotoolbox")')
b=s.index('if encoder_works(app,"libx265")',a)
assert a < b, 'libx265 still precedes VideoToolbox'
print('PASS: hardware-first source ordering + no final faststart')
PY
TMP="$(mktemp -d /tmp/endlume-847-perf.XXXXXX)"; trap 'rm -rf "$TMP"' EXIT
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x20242a:s=1920x1080:r=30:d=1' -frames:v 1 -c:v hevc_videotoolbox -realtime 1 -prio_speed 1 -power_efficient 0 -b:v 500k -maxrate 4M -bufsize 16M -g 900 -tag:v hvc1 -pix_fmt yuv420p -y "$TMP/probe.mov"
[[ -s "$TMP/probe.mov" ]] || fail 'hevc_videotoolbox smoke failed'
START="$(python3 -c 'import time;print(time.monotonic())')"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x20242a:s=1920x1080:r=30:d=30' -vf "drawbox=x='mod(t*300,1600)':y=500:w=300:h=80:color=white@0.7:t=fill" -an -c:v hevc_videotoolbox -realtime 1 -prio_speed 1 -power_efficient 0 -b:v 500k -maxrate 4M -bufsize 16M -g 900 -tag:v hvc1 -pix_fmt yuv420p -y "$TMP/perf.mov"
END="$(python3 -c 'import time;print(time.monotonic())')"
"$FFPROBE" -v error -select_streams v:0 -show_entries stream=width,height,codec_name,r_frame_rate,avg_frame_rate -of json "$TMP/perf.mov" > "$TMP/meta.json"
python3 - "$TMP/meta.json" "$START" "$END" <<'PY'
import json,sys
j=json.load(open(sys.argv[1])); s=j['streams'][0]; elapsed=float(sys.argv[3])-float(sys.argv[2])
assert s['width']==1920 and s['height']==1080, s
assert s['codec_name'] in ('hevc','h265'), s
assert elapsed < 12.0, f'VideoToolbox 30s synthetic encode too slow: {elapsed:.3f}s'
print(f'PASS: Apple VideoToolbox 30s synthetic 1080p encode {elapsed:.3f}s')
PY
echo '✅ ENDLUME 8.47 PERFORMANCE GATE PASS'
echo '✅ Apple VideoToolbox first; libx265 fallback only'
echo '✅ exact 1920x1080 + 500k video budget preserved'
echo '✅ final stream-copy mux avoids whole-file faststart relocation'
echo '✅ bounded FFprobe + 8.46 watchdog preserved'
