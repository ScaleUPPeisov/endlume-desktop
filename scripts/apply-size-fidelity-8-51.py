#!/usr/bin/env python3
from pathlib import Path
import re,sys

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()

def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.51 size: missing {rel}')
    return p

def must(cond,msg):
    if not cond: raise SystemExit('8.51 size: '+msg)

p=need('src-tauri/src/render.rs')
s=p.read_text(encoding='utf-8')

# The q100 VideoToolbox profile preserved fidelity but behaved like quality/CQ
# on the real project and produced ~2.51 Mbit/s video / 2.48 GB output. Replace
# ONLY the video rate-control profile. Audio paths are intentionally untouched.
old_vt='vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"]'
new_vt='vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-b:v","400k","-maxrate","12M","-bufsize","64M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"]'
must(old_vt in s or new_vt in s,'q100 VideoToolbox profile not found')
if old_vt in s:s=s.replace(old_vt,new_vt,1)

# Keep a high-quality software fallback under the same compact ceiling.
s=s.replace('"-crf","18","-maxrate","500k","-bufsize","4M"','"-crf","18","-maxrate","400k","-bufsize","4M"',1)
s=s.replace('fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}','fn hybrid_video_kbps(_s:&RenderSettings)->u64{400}',1)

# Rate control changed, therefore invalidate only reusable visual caches. Audio
# cache keys and audio codecs remain exactly as before.
s=s.replace('RENDER_CACHE_GENERATION:&str="8.50-speed-quality-q100-v1"','RENDER_CACHE_GENERATION:&str="8.51-size400-fidelity-v1"',1)

# Diagnostics must report the real compact profile, not the obsolete q100 mode.
s=s.replace('8.50 encoder={} hardware_first={} final_faststart=false target_video_kbps=500 q100=true','8.51 encoder={} hardware_first={} final_faststart=false target_video_kbps=400 size_target_mb=500-700 q100=false',1)

for marker in [
    'attempt==1&&encoder_works(app,"hevc_videotoolbox")',
    '"-prio_speed","0","-power_efficient","0","-b:v","400k","-maxrate","12M","-bufsize","64M"',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{400}',
    'RENDER_CACHE_GENERATION:&str="8.51-size400-fidelity-v1"',
    'let idx=i%durations.len();',
    'let duration_mode=if smart_repeat_project(job){"whole-track"}else{job.settings.duration_mode.as_str()};',
    'FFMPEG_STALL_TIMEOUT_SECS:u64=120',
]: must(marker in s,'postcondition missing: '+marker)
must('"-q:v","100"' not in s,'q100 still survives in runtime video profile')
must('if t-target<=240.0{t}else{target}' not in s,'legacy song-cut cap returned')

p.write_text(s,encoding='utf-8')
print('ENDLUME 8.51 compact 400k fidelity profile: PASS')
