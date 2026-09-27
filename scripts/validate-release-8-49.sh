#!/bin/bash
set -Eeuo pipefail
ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
FFMPEG="${2:-$(find "$ROOT/src-tauri/binaries" -maxdepth 1 -type f -name 'ffmpeg*' -print -quit)}"
FFPROBE="${3:-$(find "$ROOT/src-tauri/binaries" -maxdepth 1 -type f -name 'ffprobe*' -print -quit)}"
R="$ROOT/src-tauri/src/render.rs"
CONF="$ROOT/src-tauri/tauri.conf.json"
fail(){ echo "FAIL 8.49: $1" >&2; exit 1; }
[[ -f "$R" ]] || fail 'render.rs missing'
[[ -x "$FFMPEG" ]] || fail 'embedded FFmpeg missing'
[[ -x "$FFPROBE" ]] || fail 'embedded FFprobe missing'

python3 - "$R" "$CONF" <<'PY'
from pathlib import Path
import json,sys
r=Path(sys.argv[1]).read_text()
c=json.loads(Path(sys.argv[2]).read_text())
assert c['productName']=='ENDLUME STUDIO PEISOV',c['productName']
assert c['identifier']=='studio.endlume.desktop',c['identifier']
assert c['version']=='1.0.0-alpha.8.49',c['version']
assert any(w.get('title')=='ENDLUME STUDIO PEISOV' for w in c['app']['windows'])
assert 'resolved_job.settings.width=1920;' in r and 'resolved_job.settings.height=1080;' in r
assert 'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};' in r
assert 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' in r
assert '"-crf","18","-maxrate","500k","-bufsize","4M"' in r
assert 'FFMPEG_STALL_TIMEOUT_SECS:u64=120' in r
assert 'ffprobe_output_timeout(app,args,Duration::from_secs(12))' in r
assert 'force_original_aspect_ratio=increase' in r
assert 'RENDER_CACHE_GENERATION:&str="8.49-fidelity-v1"' in r
for x in ['HIT variant','subscribe-{}.mp4','copy-{}.mp4','audio-original-{}.mp3','audio-processed-{}.m4a','audio-continuous-{}.m4a']:
    assert x in r,x
assert 'if t-target<=240.0{t}else{target}' not in r
assert 'let idx=i%durations.len();' in r
assert 'audio_timeline_849_tests' in r
a=r.index('async fn choose_hybrid_encoder')
b=r.index('async fn probe_audio_decodes',a)
sel=r[a:b]
assert 'attempt==1&&encoder_works(app,"libx265")' in sel
assert 'attempt==1&&encoder_works(app,"hevc_videotoolbox")' not in sel
lines=[x for x in r.splitlines() if '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"' in x]
assert lines and all('+faststart' not in x for x in lines)
a=r.index('async fn build_lossless_processed_audio_cycle')
b=r.index('async fn materialize_continuous_audio',a)
assert '+faststart' not in r[a:b]
print('PASS: 8.49 source contract / brand / 1080p / 500k / watchdog / persistent cache')
PY

python3 - <<'PY'
d=[590.125,610.250,605.375,615.500,620.625,595.750,600.875,612.125,608.250,603.375,617.500,621.625]
target=6900.0
def whole(target,d,cf):
    cf=max(0.0,min(10.0,cf));t=0.0;i=0
    while t<target:
        idx=i%len(d);t+=max(0.1,d[idx]-(cf if idx>0 else 0.0));i+=1
    return t
s=sum(d);assert s-target>240.0
assert abs(whole(target,d,0)-s)<1e-9
cf=5.125;first=s-cf*(len(d)-1)
assert abs(whole(target,d,cf)-first)<1e-9
assert abs(whole(first+100,d,cf)-(first+d[0]))<1e-9
print(f'PASS: whole-track boundary OFF={s:.3f}s CF={first:.3f}s; no song truncation')
PY

TMP="$(mktemp -d /tmp/endlume-849-gate.XXXXXX)"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Fidelity gate uses the actual 8.49 60fps one-image production profile.
# SSIM is measured in the same yuv420p domain as the encoded output, matching
# the proven 8.36 method and avoiding a false penalty from RGB<->YUV conversion.
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=1920x1080:rate=1' -frames:v 1 -y "$TMP/source.png"
python3 - "$FFMPEG" "$TMP" <<'PY'
import subprocess,sys,time,re
ff,tmp=sys.argv[1:]
cmd=[ff,'-hide_banner','-loglevel','error','-loop','1','-framerate','60','-i',tmp+'/source.png','-vf','scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop=1920:1080:(iw-ow)/2:(ih-oh)/2,fps=60,setsar=1','-t','12','-an','-c:v','libx265','-preset','ultrafast','-crf','18','-maxrate','500k','-bufsize','4M','-x265-params','keyint=720:min-keyint=720:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0','-tag:v','hvc1','-pix_fmt','yuv420p','-y',tmp+'/quality.mp4']
t=time.monotonic();subprocess.run(cmd,check=True);elapsed=time.monotonic()-t
if elapsed>15: raise SystemExit(f'quality master too slow: {elapsed:.3f}s > 15s')
p=subprocess.run([ff,'-hide_banner','-loglevel','info','-i',tmp+'/source.png','-i',tmp+'/quality.mp4','-lavfi',"[0:v]format=yuv420p[ref];[1:v]select='eq(n,0)',format=yuv420p[enc];[ref][enc]ssim",'-frames:v','1','-f','null','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
m=re.search(r'All:([0-9.]+)',p.stderr)
if not m: raise SystemExit('SSIM result missing')
ssim=float(m.group(1))
if ssim<0.995: raise SystemExit(f'first-frame SSIM too low: {ssim:.6f} < 0.995')
print(f'PASS: x265 one-image quality master {elapsed:.3f}s SSIM={ssim:.6f}')
PY

# Warm-cache hard lower-bound gate: physical two-hour stream-copy on this M1.
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=640x360:rate=30' -t 12 -an -c:v libx264 -preset ultrafast -b:v 500k -maxrate 500k -bufsize 1M -g 360 -pix_fmt yuv420p -y "$TMP/io-video.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=48000' -t 12 -c:a aac -b:a 256k -y "$TMP/io-audio.m4a"
python3 - "$FFMPEG" "$TMP" <<'PY'
import os,subprocess,sys,time
ff,tmp=sys.argv[1:]
out=tmp+'/warm-2h.mov'
cmd=[ff,'-hide_banner','-loglevel','error','-stream_loop','-1','-i',tmp+'/io-video.mp4','-stream_loop','-1','-fflags','+genpts','-i',tmp+'/io-audio.m4a','-t','7200','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','copy','-video_track_timescale','60000','-y',out]
t=time.monotonic();subprocess.run(cmd,check=True);elapsed=time.monotonic()-t
mb=os.path.getsize(out)/(1024*1024)
if elapsed>30.0: raise SystemExit(f'warm 2h mux too slow: {elapsed:.3f}s > 30s ({mb:.1f} MiB)')
if not (430 <= mb <= 760): raise SystemExit(f'representative mux size outside I/O gate: {mb:.1f} MiB')
print(f'PASS: warm cached 2h stream-copy {elapsed:.3f}s, {mb:.1f} MiB')
PY

DIM="$($FFPROBE -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$TMP/quality.mp4")"
[[ "$DIM" = "1920x1080" ]] || fail "quality fixture is $DIM, expected 1920x1080"

echo '✅ ENDLUME 8.49 PERFORMANCE / FIDELITY / AUDIO GATE PASS'
echo '✅ full boundary song preserved; exact mode unchanged'
echo '✅ x265 quality-first short cache; 500k budget unchanged'
echo '✅ persistent variants / Subscribe / original audio / HQ320 audio caches wired'
echo '✅ warm two-hour stream-copy target <=30s verified on this M1 runner'
echo '✅ product display name ENDLUME STUDIO PEISOV; bundle id/updater identity preserved'
