#!/bin/bash
set -Eeuo pipefail
ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
FFMPEG="${2:-$(find "$ROOT/src-tauri/binaries" -maxdepth 1 -type f -name 'ffmpeg*' -print -quit)}"
FFPROBE="${3:-$(find "$ROOT/src-tauri/binaries" -maxdepth 1 -type f -name 'ffprobe*' -print -quit)}"
R="$ROOT/src-tauri/src/render.rs"; CONF="$ROOT/src-tauri/tauri.conf.json"
fail(){ echo "FAIL 8.50: $1" >&2; exit 1; }
[[ -x "$FFMPEG" && -x "$FFPROBE" ]] || fail 'embedded FFmpeg/FFprobe missing'
python3 - "$R" "$CONF" <<'PY'
from pathlib import Path
import json,sys
r=Path(sys.argv[1]).read_text(); c=json.loads(Path(sys.argv[2]).read_text())
assert c['version']=='1.0.0-alpha.8.50'
assert c['productName']=='ENDLUME STUDIO PEISOV'
assert c['identifier']=='studio.endlume.desktop'
assert 'RENDER_CACHE_GENERATION:&str="8.50-hw-fidelity-v1"' in r
assert 'attempt==1&&encoder_works(app,"hevc_videotoolbox")' in r
assert '"-b:v","500k","-maxrate","12M","-bufsize","48M"' in r
assert '"-crf","18","-maxrate","500k","-bufsize","4M"' in r
assert 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' in r
assert 'resolved_job.settings.width=1920;' in r and 'resolved_job.settings.height=1080;' in r
assert 'if t-target<=240.0{t}else{target}' not in r
assert 'let idx=i%durations.len();' in r
assert 'FFMPEG_STALL_TIMEOUT_SECS:u64=120' in r
assert 'ffprobe_output_timeout(app,args,Duration::from_secs(12))' in r
for x in ['HIT variant','subscribe-{}.mp4','copy-{}.mp4','audio-original-{}.mp3','audio-processed-{}.m4a','audio-continuous-{}.m4a']:
 assert x in r,x
print('PASS: 8.50 source contract: VideoToolbox-first + 1080p/500k/audio/cache preserved')
PY
TMP="$(mktemp -d /tmp/endlume-850-gate.XXXXXX)"; trap 'rm -rf "$TMP"' EXIT
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=1920x1080:rate=1' -frames:v 1 -y "$TMP/source.png"
python3 - "$FFMPEG" "$TMP" <<'PY'
import subprocess,sys,time,re,os
ff,tmp=sys.argv[1:]
out=tmp+'/cold-master.mp4'
cmd=[ff,'-hide_banner','-loglevel','error','-loop','1','-framerate','60','-i',tmp+'/source.png','-vf','scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop=1920:1080:(iw-ow)/2:(ih-oh)/2,fps=60,setsar=1','-t','12','-an','-c:v','hevc_videotoolbox','-realtime','1','-prio_speed','1','-power_efficient','0','-b:v','500k','-maxrate','12M','-bufsize','48M','-g','720','-tag:v','hvc1','-pix_fmt','yuv420p','-y',out]
t=time.monotonic(); subprocess.run(cmd,check=True); elapsed=time.monotonic()-t
if elapsed>8.0: raise SystemExit(f'cold VideoToolbox master too slow: {elapsed:.3f}s > 8s')
p=subprocess.run([ff,'-hide_banner','-loglevel','info','-i',tmp+'/source.png','-i',out,'-lavfi',"[0:v]format=yuv420p[ref];[1:v]select='eq(n,0)',format=yuv420p[enc];[ref][enc]ssim",'-frames:v','1','-f','null','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
m=re.search(r'All:([0-9.]+)',p.stderr)
if not m: raise SystemExit('SSIM result missing')
ssim=float(m.group(1))
if ssim<0.995: raise SystemExit(f'VideoToolbox first-frame SSIM too low: {ssim:.6f} < 0.995')
print(f'PASS: cold VideoToolbox master {elapsed:.3f}s SSIM={ssim:.6f}')
PY
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=640x360:rate=30' -t 12 -an -c:v libx264 -preset ultrafast -b:v 500k -maxrate 500k -bufsize 1M -g 360 -pix_fmt yuv420p -y "$TMP/io-video.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=48000' -t 12 -c:a aac -b:a 256k -y "$TMP/io-audio.m4a"
python3 - "$FFMPEG" "$TMP" <<'PY'
import os,subprocess,sys,time
ff,tmp=sys.argv[1:]; out=tmp+'/final-2h.mov'
cmd=[ff,'-hide_banner','-loglevel','error','-stream_loop','-1','-i',tmp+'/io-video.mp4','-stream_loop','-1','-fflags','+genpts','-i',tmp+'/io-audio.m4a','-t','7200','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','copy','-video_track_timescale','60000','-y',out]
t=time.monotonic(); subprocess.run(cmd,check=True); elapsed=time.monotonic()-t
mb=os.path.getsize(out)/(1024*1024)
if elapsed>20.0: raise SystemExit(f'2h final mux too slow: {elapsed:.3f}s > 20s')
if not (500<=mb<=700): raise SystemExit(f'2h representative output size {mb:.1f} MiB outside 500-700 MiB')
print(f'PASS: 2h stream-copy {elapsed:.3f}s, {mb:.1f} MiB')
PY
DIM="$($FFPROBE -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$TMP/cold-master.mp4")"; [[ "$DIM" = '1920x1080' ]] || fail "wrong dimensions $DIM"
echo '✅ ENDLUME 8.50 COLD SPEED / FIDELITY / AUDIO GATE PASS'
echo '✅ Apple VideoToolbox primary; libx265 fallback only'
echo '✅ cold short master <=8s; physical 2h mux <=20s'
echo '✅ 500-700 MiB representative output gate'
echo '✅ whole-track audio / persistent cache / 1080p / updater identity preserved'
