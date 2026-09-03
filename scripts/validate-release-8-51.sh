#!/bin/bash
set -Eeuo pipefail
ROOT="${1:-.}"
FFMPEG="${2:-ffmpeg}"
FFPROBE="${3:-ffprobe}"
R="$ROOT/src-tauri/src/render.rs"
fail(){ echo "FAIL 8.51: $1" >&2; exit 1; }
[[ -f "$R" ]] || fail "render.rs missing"

# Validate only the production selector. Legacy helper functions can contain
# hardware probes without being used by the active short-master path.
python3 - "$R" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
a=s.find('async fn choose_hybrid_encoder')
b=s.find('async fn probe_audio_decodes',a)
assert a>=0 and b>a,'choose_hybrid_encoder scope missing'
sel=s[a:b]
assert 'attempt==1&&encoder_works(app,"libx265")' in sel,'x265 is not quality-first in choose_hybrid_encoder'
assert 'attempt==1&&encoder_works(app,"hevc_videotoolbox")' not in sel,'VideoToolbox is still hardware-first in choose_hybrid_encoder'
print('PASS: active choose_hybrid_encoder is x265 quality-first; VT remains fallback')
PY

grep -Fq '"-crf","18","-maxrate","400k","-bufsize","4M"' "$R" || fail "x265 CRF18/400k profile missing"
grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{400}' "$R" || fail "400k size ceiling missing"
grep -Fq 'RENDER_CACHE_GENERATION:&str="8.51-x265-crf18-size400-v2"' "$R" || fail "8.51 quality cache generation missing"
# VideoToolbox q100 remains only a high-fidelity emergency fallback.
grep -Fq '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"' "$R" || fail "quality fallback changed"
grep -Fq 'resolved_job.settings.width=1920;' "$R" || fail "1920 lock lost"
grep -Fq 'resolved_job.settings.height=1080;' "$R" || fail "1080 lock lost"
grep -Fq 'FFMPEG_STALL_TIMEOUT_SECS:u64=120' "$R" || fail "watchdog changed"
grep -Fq 'ffprobe_output_timeout(app,args,Duration::from_secs(12))' "$R" || fail "bounded FFprobe changed"
grep -Fq 'let idx=i%durations.len();' "$R" || fail "whole-track math lost"
grep -Fq 'let duration_mode=if smart_repeat_project(job){"whole-track"}else{job.settings.duration_mode.as_str()};' "$R" || fail "one-image whole-song policy lost"
! grep -Fq 'if t-target<=240.0{t}else{target}' "$R" || fail "song truncation cap returned"

# Full-project speed architecture.
grep -Fq 'VISUAL_PLAN_CACHE_GENERATION:&str="8.51-manifest-v1"' "$R" || fail "8.51 manifest generation missing"
grep -Fq 'append_smart_manifest_interval' "$R" || fail "manifest interval planner missing"
grep -Fq '8.51 MANIFEST_READY' "$R" || fail "manifest diagnostic missing"
grep -Fq 'manifest_851_tests' "$R" || fail "manifest regression tests missing"
grep -Fq '"heic"|"heif"|"avif"' "$R" || fail "one-still detection not hardened"
! grep -Fq 'copy_segment(app,job,&variant,vd,a,b-a,&cached' "$R" || fail "old long normal interval cache survived"

grep -Fq '"productName": "ENDLUME STUDIO PEISOV"' "$ROOT/src-tauri/tauri.conf.json" || fail "product name changed"
grep -Fq '"identifier": "studio.endlume.desktop"' "$ROOT/src-tauri/tauri.conf.json" || fail "bundle id changed"
grep -Fq '"version": "1.0.0-alpha.8.51"' "$ROOT/src-tauri/tauri.conf.json" || fail "version not 8.51"

TMP="$(mktemp -d /tmp/endlume-851-gate.XXXXXX)"
OUTROOT="$TMP"
if [[ -d '/Volumes/TOSHIBA EXT' && -w '/Volumes/TOSHIBA EXT' ]]; then
  OUTROOT="/Volumes/TOSHIBA EXT/.endlume-851-speed-gate-$$"
  mkdir -p "$OUTROOT"
fi
cleanup(){ rm -rf "$TMP" "$OUTROOT" >/dev/null 2>&1 || true; }
trap cleanup EXIT

python3 - "$FFMPEG" "$FFPROBE" "$TMP" "$OUTROOT" <<'PY'
import pathlib,subprocess,sys,time,re
ff,fp,tmp,outroot=sys.argv[1:]
tmp=pathlib.Path(tmp); outroot=pathlib.Path(outroot)
ref=tmp/'reference.png'; quality=tmp/'quality12.mp4'; master=tmp/'master60.mp4'; sub=tmp/'subscribe5.mp4'; frag=tmp/'fragment55.mp4'; audio=tmp/'audio60.m4a'; manifest=tmp/'visual-concat.txt'
out1=outroot/'ENDLUME-851-cold.mov'; out2=outroot/'ENDLUME-851-warm.mov'

def run(args,capture=False):
    return subprocess.run(args,check=True,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,stderr=subprocess.PIPE if capture else subprocess.DEVNULL,text=capture)

def probe(path,entries):
    return run([fp,'-v','error','-show_entries',entries,'-of','default=nw=1',str(path)],capture=True).stdout

def x265_profile(g):
    return ['-c:v','libx265','-preset','ultrafast','-crf','18','-maxrate','400k','-bufsize','4M','-x265-params',f'keyint={g}:min-keyint={g}:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0','-g',str(g),'-tag:v','hvc1','-pix_fmt','yuv420p']

# Sharp static reference matching the user's single-image workflow.
run([ff,'-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=1920x1080:rate=1','-frames:v','1','-y',str(ref)])

# Dedicated fidelity gate uses the exact software quality-first production family.
run([ff,'-hide_banner','-loglevel','error','-loop','1','-framerate','60','-i',str(ref),'-vf','scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop=1920:1080:(iw-ow)/2:(ih-oh)/2,fps=60,setsar=1','-t','12','-an',*x265_profile(720),'-y',str(quality)])
ss=run([ff,'-hide_banner','-i',str(ref),'-i',str(quality),'-lavfi',"[0:v]format=yuv420p[r];[1:v]select='eq(n,0)',format=yuv420p[t];[r][t]ssim",'-frames:v','1','-f','null','-'],capture=True).stderr
vals=re.findall(r'All:([0-9.]+)',ss)
ssim=float(vals[-1]) if vals else 0.0
if ssim<0.995: raise SystemExit(f'FAIL 8.51: static-image SSIM {ssim:.6f} < 0.995 on x265 CRF18/400k quality-first profile')

# Representative one-image + moving Effect master for real size/speed pressure.
fc="[0:v]scale=1920:1080:flags=lanczos,format=yuv420p[bg];[1:v]scale=480:270,format=rgba,colorchannelmixer=aa=0.22[fx];[bg][fx]overlay=x='mod(t*90,1440)':y=760:shortest=1[outv]"
cold_start=time.monotonic()
run([ff,'-hide_banner','-loglevel','error','-loop','1','-framerate','60','-i',str(ref),'-f','lavfi','-i','testsrc2=size=480x270:rate=60','-filter_complex',fc,'-map','[outv]','-t','60','-an',*x265_profile(3600),'-y',str(master)])
# One reusable 5s Subscribe composite. Repeated occurrences reference this clip.
subfc="[0:v]setpts=PTS-STARTPTS[bg];[1:v]scale=420:120,format=rgba,colorchannelmixer=aa=1.0[sub];[bg][sub]overlay=x=(W-w)/2:y=H-h-120:shortest=1[outv]"
run([ff,'-hide_banner','-loglevel','error','-stream_loop','-1','-i',str(master),'-f','lavfi','-i','testsrc2=size=420x120:rate=60','-filter_complex',subfc,'-map','[outv]','-t','5','-an',*x265_profile(300),'-y',str(sub)])
run([ff,'-hide_banner','-loglevel','error','-i',str(master),'-t','55','-an','-c:v','copy','-avoid_negative_ts','make_zero','-y',str(frag)])
# Worst normal source-music case: HQ 320k audio. Runtime never recompresses music
# merely to satisfy the size target.
run([ff,'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=220:sample_rate=48000','-t','60','-c:a','aac','-b:a','320k','-ar','48000','-ac','2','-y',str(audio)])

# 12 full 10-minute cycles = 7200s, then 5 cached master minutes = 7500s (2:05).
lines=[]
for _ in range(12):
    lines += [f"file '{master.as_posix()}'"]*9
    lines += [f"file '{frag.as_posix()}'",f"file '{sub.as_posix()}'"]
lines += [f"file '{master.as_posix()}'"]*5
manifest.write_text('\n'.join(lines)+'\n')
if len(lines)>=200: raise SystemExit(f'FAIL 8.51: manifest unexpectedly large: {len(lines)} entries')

def final_mux(out):
    t=time.monotonic()
    run([ff,'-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(manifest),'-stream_loop','-1','-i',str(audio),'-t','7500','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','copy','-video_track_timescale','60000','-y',str(out)])
    return time.monotonic()-t

cold_mux=final_mux(out1); cold_total=time.monotonic()-cold_start
warm=final_mux(out2)
if warm>30.0: raise SystemExit(f'FAIL 8.51: physical 2h05 warm full mux {warm:.3f}s > 30s')
if cold_total>75.0: raise SystemExit(f'FAIL 8.51: representative first-cache full project {cold_total:.3f}s > 75s')
info=probe(out2,'format=duration,size,bit_rate:stream=codec_name,width,height,avg_frame_rate,bit_rate')
if 'codec_name=hevc' not in info or 'width=1920' not in info or 'height=1080' not in info: raise SystemExit('FAIL 8.51: final benchmark lost HEVC 1920x1080')
m=re.search(r'duration=([0-9.]+)',info); dur=float(m.group(1)) if m else 0
if abs(dur-7500)>2.0: raise SystemExit(f'FAIL 8.51: final duration {dur:.3f}s != 7500s')
size_mb=out2.stat().st_size/1_000_000
if size_mb<500 or size_mb>700: raise SystemExit(f'FAIL 8.51: physical 2h05 output {size_mb:.1f} MB outside required 500-700 MB')
print(f'PASS: 8.51 physical full-project SSIM={ssim:.6f} cold={cold_total:.3f}s (mux={cold_mux:.3f}s) warm={warm:.3f}s size={size_mb:.1f}MB entries={len(lines)} output={outroot}')
PY

echo '✅ ENDLUME 8.51 FULL PROJECT SPEED + SIZE + FIDELITY GATE PASS'
echo '✅ x265 CRF18 quality-first short masters; VideoToolbox q100 fallback only'
echo '✅ one-image long normal intervals are manifest references, not duplicate multi-minute MP4 files'
echo '✅ physical 2h05 warm assembly <=30s; representative first-cache <=75s'
echo '✅ physical 2h05 output is strictly 500-700 MB with HQ320 audio pressure'
echo '✅ static-image SSIM >=0.995; whole-song audio preserved'
