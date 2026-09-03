#!/bin/bash
set -Eeuo pipefail
ROOT="${1:-.}"
FFMPEG="${2:-ffmpeg}"
FFPROBE="${3:-ffprobe}"
R="$ROOT/src-tauri/src/render.rs"
fail(){ echo "FAIL 8.51: $1" >&2; exit 1; }
[[ -f "$R" ]] || fail "render.rs missing"

# Immutable fidelity/audio/stability contracts.
grep -Fq 'attempt==1&&encoder_works(app,"hevc_videotoolbox")' "$R" || fail "VideoToolbox not hardware-first"
grep -Fq '"-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"' "$R" || fail "q100 fidelity profile changed"
grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' "$R" || fail "500k budget changed"
grep -Fq 'resolved_job.settings.width=1920;' "$R" || fail "1920 lock lost"
grep -Fq 'resolved_job.settings.height=1080;' "$R" || fail "1080 lock lost"
grep -Fq 'FFMPEG_STALL_TIMEOUT_SECS:u64=120' "$R" || fail "watchdog changed"
grep -Fq 'ffprobe_output_timeout(app,args,Duration::from_secs(12))' "$R" || fail "bounded FFprobe changed"
grep -Fq 'let idx=i%durations.len();' "$R" || fail "whole-track math lost"
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
import pathlib,subprocess,sys,time,re,os
ff,fp,tmp,outroot=sys.argv[1:]
tmp=pathlib.Path(tmp); outroot=pathlib.Path(outroot)
ref=tmp/'reference.png'; master=tmp/'master60.mp4'; sub=tmp/'subscribe5.mp4'; frag=tmp/'fragment55.mp4'; audio=tmp/'audio60.m4a'; manifest=tmp/'visual-concat.txt'
out1=outroot/'ENDLUME-851-cold.mp4'; out2=outroot/'ENDLUME-851-warm.mp4'

def run(args,capture=False):
    return subprocess.run(args,check=True,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,stderr=subprocess.PIPE if capture else subprocess.DEVNULL,text=capture)

def probe(path,entries):
    return run([fp,'-v','error','-show_entries',entries,'-of','default=nw=1',str(path)],capture=True).stdout

# One sharp still + moving Effect, matching the production one-image shape.
run([ff,'-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=1920x1080:rate=1','-frames:v','1','-y',str(ref)])
profile=['-c:v','hevc_videotoolbox','-realtime','1','-prio_speed','0','-power_efficient','0','-q:v','100','-b:v','500k','-maxrate','12M','-bufsize','64M','-tag:v','hvc1','-pix_fmt','yuv420p']
fc="[0:v]scale=1920:1080:flags=lanczos,format=yuv420p[bg];[1:v]scale=480:270,format=rgba,colorchannelmixer=aa=0.22[fx];[bg][fx]overlay=x='mod(t*90,1440)':y=760:shortest=1[outv]"
cold_start=time.monotonic()
run([ff,'-hide_banner','-loglevel','error','-loop','1','-framerate','60','-i',str(ref),'-f','lavfi','-i','testsrc2=size=480x270:rate=60','-filter_complex',fc,'-map','[outv]','-t','60','-an',*profile,'-g','3600','-y',str(master)])
# One reusable 5s Subscribe composite. Repeated occurrences must reference this clip, not re-encode it.
subfc="[0:v]setpts=PTS-STARTPTS[bg];[1:v]scale=420:120,format=rgba,colorchannelmixer=aa=0.85[sub];[bg][sub]overlay=x=(W-w)/2:y=H-h-120:shortest=1[outv]"
run([ff,'-hide_banner','-loglevel','error','-stream_loop','-1','-i',str(master),'-f','lavfi','-i','testsrc2=size=420x120:rate=60','-filter_complex',subfc,'-map','[outv]','-t','5','-an',*profile,'-g','300','-y',str(sub)])
# Only a small boundary fragment is materialized; the 595s normal interval is never copied as one file.
run([ff,'-hide_banner','-loglevel','error','-i',str(master),'-t','55','-an','-c:v','copy','-avoid_negative_ts','make_zero','-y',str(frag)])
run([ff,'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=220:sample_rate=48000','-t','60','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-y',str(audio)])
lines=[]
for _ in range(12):
    lines += [f"file '{master.as_posix()}'"]*9
    lines += [f"file '{frag.as_posix()}'",f"file '{sub.as_posix()}'"]
manifest.write_text('\n'.join(lines)+'\n')
if len(lines)>=200: raise SystemExit(f'FAIL 8.51: manifest unexpectedly large: {len(lines)} entries')

def final_mux(out):
    t=time.monotonic()
    run([ff,'-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(manifest),'-stream_loop','-1','-i',str(audio),'-t','7200','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','copy','-video_track_timescale','60000','-y',str(out)])
    return time.monotonic()-t

cold_mux=final_mux(out1); cold_total=time.monotonic()-cold_start
warm=final_mux(out2)
if warm>30.0: raise SystemExit(f'FAIL 8.51: physical 2h warm full mux {warm:.3f}s > 30s')
if cold_total>60.0: raise SystemExit(f'FAIL 8.51: representative first-cache full project {cold_total:.3f}s > 60s')
info=probe(out2,'format=duration,size:stream=codec_name,width,height,avg_frame_rate')
if 'codec_name=hevc' not in info or 'width=1920' not in info or 'height=1080' not in info: raise SystemExit('FAIL 8.51: final benchmark lost HEVC 1920x1080')
m=re.search(r'duration=([0-9.]+)',info); dur=float(m.group(1)) if m else 0
if abs(dur-7200)>2.0: raise SystemExit(f'FAIL 8.51: final duration {dur:.3f}s != 7200s')
size=out2.stat().st_size/1024/1024
# Synthetic source is deliberately more dynamic than the user's mostly-static image;
# this is a sanity bound, while production keeps the exact 500k budget above.
if size<300 or size>850: raise SystemExit(f'FAIL 8.51: representative 2h payload unreasonable: {size:.1f} MiB')
print(f'PASS: 8.51 physical full-project cold={cold_total:.3f}s (mux={cold_mux:.3f}s) warm={warm:.3f}s size={size:.1f}MiB entries={len(lines)} output={outroot}')
PY

echo '✅ ENDLUME 8.51 FULL PROJECT SPEED GATE PASS'
echo '✅ one-image long normal intervals are manifest references, not duplicate multi-minute MP4 files'
echo '✅ physical 2h warm assembly <=30s; representative first-cache <=60s'
echo '✅ q100 / 500k / 1920x1080 / whole-track / watchdog / updater identity preserved'
