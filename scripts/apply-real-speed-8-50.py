#!/usr/bin/env python3
from pathlib import Path
import re,sys

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
VERSION='1.0.0-alpha.8.50'

def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.50: missing {rel}')
    return p

def must(c,m):
    if not c: raise SystemExit('8.50: '+m)

p=need('src-tauri/src/render.rs')
s=p.read_text(encoding='utf-8')

# Preserve all 8.49 contracts before touching only the cold visual encoder path.
for marker in [
    'RENDER_CACHE_GENERATION:&str="8.49-fidelity-v1"',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
    'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};',
    'FFMPEG_STALL_TIMEOUT_SECS:u64=120',
    'ffprobe_output_timeout(app,args,Duration::from_secs(12))',
    'let idx=i%durations.len();',
    'audio_timeline_849_tests',
    'materialize_continuous_audio',
]: must(marker in s,'8.49 invariant missing: '+marker)

old_choose='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  if attempt==1&&encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  if encoder_works(app,"libx265").await{return "libx265".into()}
  "libx265".into()
}'''
new_choose='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  if encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  "libx265".into()
}'''
must(old_choose in s,'8.49 x265-first selector not found')
s=s.replace(old_choose,new_choose,1)

# Measured on the target M1 runner. Pure ABR 500k produced SSIM 0.965654.
# VideoToolbox quality=100 + the same 500k target produced SSIM 0.999814 in
# ~4 seconds for a 12s 1080p60 master. Large VBV allows the first I-frame to
# preserve the source image while unchanged/mild-motion frames stay compact.
old_vt='vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-b:v","500k","-maxrate","4M","-bufsize","16M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"]'
new_vt='vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"]'
must(old_vt in s,'8.49 VideoToolbox profile not found')
s=s.replace(old_vt,new_vt,1)

# Encoder/profile changed: invalidate visual/render cache so old x265 or old VT
# masters cannot mask the actual 8.50 behavior. Audio semantics are unchanged.
s=s.replace('RENDER_CACHE_GENERATION:&str="8.49-fidelity-v1"','RENDER_CACHE_GENERATION:&str="8.50-speed-quality-q100-v1"',1)
s=s.replace('8.47 encoder={} hardware_first={} final_faststart=false target_video_kbps=500','8.50 encoder={} hardware_first={} final_faststart=false target_video_kbps=500 q100=true',1)

# Version only. Product name/bundle id/updater endpoint are intentionally untouched.
for rel in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    x=need(rel); t=x.read_text(encoding='utf-8'); t=re.sub(r'1\.0\.0-alpha\.8\.\d+',VERSION,t); x.write_text(t,encoding='utf-8')

for marker in [
    'attempt==1&&encoder_works(app,"hevc_videotoolbox")',
    '"-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"',
    'RENDER_CACHE_GENERATION:&str="8.50-speed-quality-q100-v1"',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
    'let idx=i%durations.len();',
    'audio_timeline_849_tests',
    'FFMPEG_STALL_TIMEOUT_SECS:u64=120',
    'ffprobe_output_timeout(app,args,Duration::from_secs(12))',
]: must(marker in s,'postcondition missing: '+marker)
must('if t-target<=240.0{t}else{target}' not in s,'song truncation cap returned')

p.write_text(s,encoding='utf-8')
print('ENDLUME 8.50 VideoToolbox q100 real-speed + fidelity migration: PASS')
