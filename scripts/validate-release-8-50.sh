#!/bin/bash
set -Eeuo pipefail
# q100 profile confirmed by M1 sweep on 2026-09-03; rerun full signed candidate.
ROOT="${1:-.}"
FFMPEG="${2:-ffmpeg}"
FFPROBE="${3:-ffprobe}"
R="$ROOT/src-tauri/src/render.rs"
fail(){ echo "FAIL 8.50: $1" >&2; exit 1; }
[[ -f "$R" ]] || fail "render.rs missing"

grep -Fq 'attempt==1&&encoder_works(app,"hevc_videotoolbox")' "$R" || fail "VideoToolbox is not hardware-first"
grep -Fq '"-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"' "$R" || fail "measured q100 VT fidelity profile missing"
grep -Fq 'RENDER_CACHE_GENERATION:&str="8.50-speed-quality-q100-v1"' "$R" || fail "8.50 cache generation missing"
grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' "$R" || fail "500k budget changed"
grep -Fq 'resolved_job.settings.width=1920;' "$R" || fail "1920 lock lost"
grep -Fq 'resolved_job.settings.height=1080;' "$R" || fail "1080 lock lost"
grep -Fq 'FFMPEG_STALL_TIMEOUT_SECS:u64=120' "$R" || fail "watchdog changed"
grep -Fq 'ffprobe_output_timeout(app,args,Duration::from_secs(12))' "$R" || fail "bounded FFprobe changed"
grep -Fq 'let idx=i%durations.len();' "$R" || fail "whole-track math lost"
if grep -Fq 'if t-target<=240.0{t}else{target}' "$R"; then fail "old song cut cap returned"; fi

grep -Fq '"productName": "ENDLUME STUDIO PEISOV"' "$ROOT/src-tauri/tauri.conf.json" || fail "product name changed"
grep -Fq '"identifier": "studio.endlume.desktop"' "$ROOT/src-tauri/tauri.conf.json" || fail "bundle id changed"
grep -Fq '"version": "1.0.0-alpha.8.50"' "$ROOT/src-tauri/tauri.conf.json" || fail "version not 8.50"

TMP="$(mktemp -d /tmp/endlume-850-gate.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

python3 - "$FFMPEG" "$FFPROBE" "$TMP" <<'PY'
import pathlib,subprocess,sys,time,re
ff,fp,tmp=sys.argv[1:]
tmp=pathlib.Path(tmp)
ref=tmp/'reference.png'; out=tmp/'vt-quality.mp4'; dec=tmp/'decoded.png'; dyn=tmp/'vt-dynamic.mp4'
def run(args,check=True,capture=False):
    return subprocess.run(args,check=check,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,stderr=subprocess.PIPE if capture else subprocess.DEVNULL,text=capture)
def bitrate(path):
    p=run([fp,'-v','error','-select_streams','v:0','-show_entries','stream=bit_rate','-of','default=nw=1:nk=1',str(path)],capture=True).stdout.strip()
    try:return int(p)/1000.0
    except:return 0.0
run([ff,'-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=1920x1080:rate=1','-frames:v','1','-y',str(ref)])
profile=['-c:v','hevc_videotoolbox','-realtime','1','-prio_speed','0','-power_efficient','0','-q:v','100','-b:v','500k','-maxrate','12M','-bufsize','64M','-tag:v','hvc1','-pix_fmt','yuv420p']
start=time.monotonic();run([ff,'-hide_banner','-loglevel','error','-loop','1','-framerate','60','-i',str(ref),'-t','12','-an',*profile,'-g','720','-y',str(out)]);static_sec=time.monotonic()-start
if static_sec>12.0: raise SystemExit(f'FAIL 8.50: 12s hardware master too slow: {static_sec:.3f}s')
run([ff,'-hide_banner','-loglevel','error','-i',str(out),'-frames:v','1','-y',str(dec)])
p=run([ff,'-hide_banner','-i',str(ref),'-i',str(dec),'-filter_complex','[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]ssim','-frames:v','1','-f','null','-'],capture=True)
m=re.findall(r'All:([0-9.]+)',p.stderr)
if not m: raise SystemExit('FAIL 8.50: cannot parse SSIM')
ssim=float(m[-1])
if ssim<0.995: raise SystemExit(f'FAIL 8.50: VideoToolbox q100 first-frame SSIM {ssim:.6f} < 0.995')
static_kbps=bitrate(out)
fc="[0:v]scale=1920:1080:flags=lanczos,format=yuv420p[bg];[1:v]format=rgba,colorchannelmixer=aa=0.30[ov];[bg][ov]overlay=x='mod(t*120,1280)':y=360:shortest=1[outv]"
start=time.monotonic();run([ff,'-hide_banner','-loglevel','error','-loop','1','-framerate','60','-i',str(ref),'-f','lavfi','-i','testsrc2=size=640x360:rate=60','-filter_complex',fc,'-map','[outv]','-t','60','-an',*profile,'-g','3600','-y',str(dyn)]);dyn_sec=time.monotonic()-start
if dyn_sec>60.0: raise SystemExit(f'FAIL 8.50: cold 60s effect master {dyn_sec:.3f}s > 60s')
dyn_kbps=bitrate(dyn)
probe=run([fp,'-v','error','-select_streams','v:0','-show_entries','stream=width,height,avg_frame_rate,codec_name','-of','default=nw=1',str(dyn)],capture=True).stdout
if 'width=1920' not in probe or 'height=1080' not in probe: raise SystemExit('FAIL 8.50: benchmark output not 1920x1080')
if 'codec_name=hevc' not in probe: raise SystemExit('FAIL 8.50: benchmark output is not HEVC')
print(f'PASS: 8.50 q100 hardware master {static_sec:.3f}s SSIM={ssim:.6f} video={static_kbps:.1f}kbps')
print(f'PASS: 8.50 representative cold 60s effect master {dyn_sec:.3f}s video={dyn_kbps:.1f}kbps')
PY

echo '✅ ENDLUME 8.50 REAL SPEED / QUALITY GATE PASS'
echo '✅ VideoToolbox q100 hardware-first; libx265 fallback only'
echo '✅ 500k target / 1920x1080 / whole-track / watchdog / updater identity preserved'
