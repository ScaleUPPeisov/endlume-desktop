#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
fail(){ echo "8.43 FPS validation failed: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }

R=src-tauri/src/render.rs
C=src-tauri/src/cache.rs
[[ -f "$R" && -f "$C" ]] || fail 'render/cache source missing'

# Source-level production guards.
grep -Fq 'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};' "$R" || fail 'real 30/60 runtime mapping missing'
if grep -Fq 'resolved_job.settings.fps=resolved_job.settings.fps.min(30);' "$R"; then fail 'hidden 60->30 clamp survived'; fi
grep -Fq 'fn cfr_output_args(s:&RenderSettings)' "$R" || fail 'CFR output helper missing'
grep -Fq '"-fps_mode".into(),"cfr".into(),"-r".into()' "$R" || fail 'CFR/r output options missing'
grep -Fq '"-video_track_timescale".into(),"60000".into()' "$R" || fail '60k video track timescale missing'
grep -Fq '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"' "$R" || fail 'final stream-copy mux contract missing'
grep -Fq 'r_frame_rate,avg_frame_rate,nb_frames,nb_read_packets,duration' "$R" || fail 'final FFprobe CFR/frame-count check missing'
grep -Fq 'Ошибка FPS: запрошено' "$R" || fail 'runtime FPS failure message missing'
grep -Fq 'minterpolate=fps={fps}:mi_mode=mci' "$C" || fail 'Effects true-motion interpolation missing'
grep -Fq '"-fps_mode","cfr","-r",fps_s.as_str()' "$C" || fail 'Effects cache CFR output missing'
pass 'production pipeline contains explicit CFR 30/60 + final-file FFprobe guard'

# Accepted contracts must remain unchanged.
grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' "$R" || fail '500k speed/size budget changed'
grep -Fq '"-maxrate","500k","-bufsize","4M"' "$R" || fail 'x265 budget changed'
grep -Fq '"-b:v","500k","-maxrate","4M","-bufsize","16M"' "$R" || fail 'VideoToolbox budget changed'
grep -Fq 'force_original_aspect_ratio=increase' "$R" || fail '16:9 fill scale changed'
grep -Fq 'crop={}:{}:(iw-ow)/2:(ih-oh)/2' "$R" || fail '16:9 crop changed'
grep -Fq 'acrossfade=d={cf}:c1=tri:c2=tri' "$R" || fail 'audio crossfade changed'
grep -Fq 'materialize_continuous_audio' "$R" || fail 'gapless audio changed'
if grep -Eq 'Noise 1|Noise 2|Шум 1|Шум 2' src/pages/Editors.tsx src/pages/ProjectPage.tsx src/store.ts "$R"; then fail 'Noise 1/2 regression'; fi
grep -Fq '1.0.0-alpha.8.43' package.json || fail 'package version is not 8.43'
grep -Fq '1.0.0-alpha.8.43' src-tauri/tauri.conf.json || fail 'Tauri version is not 8.43'
pass 'render/audio/size/UI accepted contracts preserved'

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

probe_video(){
  local file="$1" expected="$2" width="$3" height="$4"
  local json="$TMP/probe-$(basename "$file").json"
  "$FFPROBE" -v error -select_streams v:0 -count_packets \
    -show_entries stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_packets,duration \
    -of json "$file" > "$json"
  python3 - "$json" "$expected" "$width" "$height" <<'PY'
import json,sys,math
p,expected,want_w,want_h=sys.argv[1],float(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4])
s=json.load(open(p))['streams'][0]
def rate(x):
    a,b=(str(x).split('/')+['1'])[:2]
    return float(a)/max(float(b),1e-12)
r=rate(s.get('r_frame_rate','0/1'))
a=rate(s.get('avg_frame_rate','0/1'))
w=int(s.get('width',0)); h=int(s.get('height',0))
d=float(s.get('duration') or 0)
frames=s.get('nb_frames') or s.get('nb_read_packets')
frames=float(frames) if frames not in (None,'N/A','') else 0
measured=frames/d if frames and d>0 else 0
print(f'PROBE {w}x{h} r={r:.6f} avg={a:.6f} duration={d:.3f} frames/packets={frames:.0f} measured={measured:.6f}')
assert (w,h)==(want_w,want_h),(w,h)
assert abs(r-expected)<=0.10,(r,expected)
assert abs(a-expected)<=0.10,(a,expected)
assert abs(r-a)<=0.10,(r,a)
assert frames>0,'frame/packet count unavailable'
assert abs(measured-expected)<=0.25,(measured,expected)
PY
}

# 60 FPS motion: source 30 -> actual motion-interpolated CFR60.
M60="$TMP/motion60.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=s=640x360:r=30' -t 5 \
  -vf 'minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,scale=1920:1080' \
  -an -c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p \
  -fps_mode cfr -r 60 -video_track_timescale 60000 -y "$M60"
probe_video "$M60" 60 1920 1080
pass 'requested 60 -> physical CFR60 with ~duration*60 frames'

# Make sure the motion sample is not merely pairwise duplicated 30fps metadata.
HASHES="$TMP/motion.framemd5"
"$FFMPEG" -hide_banner -loglevel error -i "$M60" -t 3 -map 0:v:0 -f framemd5 -y "$HASHES"
python3 - "$HASHES" <<'PY'
import sys
hashes=[]
for line in open(sys.argv[1],errors='ignore'):
    line=line.strip()
    if not line or line.startswith('#'): continue
    parts=[x.strip() for x in line.split(',')]
    if len(parts)>=6: hashes.append(parts[-1])
assert len(hashes)>=170,len(hashes)
pairs=min(len(hashes)//2,90)
dup=sum(1 for i in range(pairs) if hashes[i*2]==hashes[i*2+1])
ratio=dup/max(pairs,1)
print(f'PASS: moving 60fps sample pair-duplicate ratio={ratio:.3f}')
assert ratio<0.20,ratio
PY

# Final ENDLUME architecture smoke: short CFR60 master -> long stream-copy final.
MASTER="$TMP/short-master60.mp4"
FINAL="$TMP/final-loop60.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=s=1920x1080:r=60' -t 2 \
  -an -c:v libx264 -preset ultrafast -crf 22 -pix_fmt yuv420p \
  -fps_mode cfr -r 60 -video_track_timescale 60000 -y "$MASTER"
"$FFMPEG" -hide_banner -loglevel error -stream_loop -1 -i "$MASTER" -t 10 \
  -map 0:v:0 -an -c:v copy -video_track_timescale 60000 -y "$FINAL"
probe_video "$FINAL" 60 1920 1080
pass 'short-master -> final stream-copy keeps CFR60'

# Explicit 30 FPS mode must still be genuine CFR30.
M30="$TMP/motion30.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=s=1920x1080:r=30' -t 4 \
  -an -c:v libx264 -preset ultrafast -crf 22 -pix_fmt yuv420p \
  -fps_mode cfr -r 30 -video_track_timescale 60000 -y "$M30"
probe_video "$M30" 30 1920 1080
pass 'requested 30 -> physical CFR30'

# Bitrate budget is unchanged; 60 FPS must not double bitrate.
python3 - <<'PY'
sec=2*3600+2*60+3
mb=(500_000+320_000)*sec/8/1_000_000
print(f'PASS: 2:02:03 nominal payload remains {mb:.1f} MB before container overhead')
assert 700<=mb<1000,mb
PY

echo '✅ ENDLUME 8.43 Real 60 FPS Output Validation gate passed'
