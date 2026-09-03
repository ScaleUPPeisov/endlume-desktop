#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()

def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.51 size: missing {rel}')
    return p

def must(cond,msg):
    if not cond: raise SystemExit('8.51 size: '+msg)

p=need('src-tauri/src/render.rs')
s=p.read_text(encoding='utf-8')

# 8.50 made VideoToolbox q100 hardware-first. On the real full-size profile that
# mode can overshoot the requested file size, while pure VT ABR 400k failed the
# physical fidelity gate (SSIM 0.959530). Restore the 8.49 quality-first selector:
# libx265 CRF18 is first for the short reusable master; VideoToolbox remains a
# high-quality fallback only.
old_choose='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  if encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  "libx265".into()
}'''
new_choose='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  if attempt==1&&encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  if encoder_works(app,"libx265").await{return "libx265".into()}
  "libx265".into()
}'''
must(old_choose in s or new_choose in s,'8.50 encoder selector not found')
if old_choose in s:s=s.replace(old_choose,new_choose,1)

# Keep CRF18 / ultrafast / long-GOP quality behavior, but cap the software
# fallback/primary at 400k. Unlike VideoToolbox ABR this still lets CRF preserve
# the first/static frame using the existing 4M VBV buffer, while 400k + HQ320
# has enough headroom to keep a 2h05 file below 700 MB.
old_x265='"-crf","18","-maxrate","500k","-bufsize","4M"'
new_x265='"-crf","18","-maxrate","400k","-bufsize","4M"'
must(old_x265 in s or new_x265 in s,'x265 CRF18 profile not found')
if old_x265 in s:s=s.replace(old_x265,new_x265,1)

# The nominal budget follows the real enforced ceiling. VideoToolbox q100 stays
# only as emergency fallback; normal one-image jobs are x265-first.
s=s.replace('fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}','fn hybrid_video_kbps(_s:&RenderSettings)->u64{400}',1)

# Encoder selection/rate-control changed, therefore invalidate visual masters.
# Audio caches/codecs are intentionally untouched.
s=s.replace('RENDER_CACHE_GENERATION:&str="8.50-speed-quality-q100-v1"','RENDER_CACHE_GENERATION:&str="8.51-x265-crf18-size400-v2"',1)

# Runtime diagnostics report the actual production policy.
s=s.replace('8.50 encoder={} hardware_first={} final_faststart=false target_video_kbps=500 q100=true','8.51 encoder={} quality_first=true final_faststart=false target_video_kbps=400 size_target_mb=500-700 vt_q100_fallback=true',1)

for marker in [
    'attempt==1&&encoder_works(app,"libx265")',
    '"-crf","18","-maxrate","400k","-bufsize","4M"',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{400}',
    'RENDER_CACHE_GENERATION:&str="8.51-x265-crf18-size400-v2"',
    '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"',
    'let idx=i%durations.len();',
    'let duration_mode=if smart_repeat_project(job){"whole-track"}else{job.settings.duration_mode.as_str()};',
    'FFMPEG_STALL_TIMEOUT_SECS:u64=120',
]: must(marker in s,'postcondition missing: '+marker)
must('attempt==1&&encoder_works(app,"hevc_videotoolbox")' not in s,'VideoToolbox is still hardware-first')
must('if t-target<=240.0{t}else{target}' not in s,'legacy song-cut cap returned')

p.write_text(s,encoding='utf-8')
print('ENDLUME 8.51 x265 CRF18 quality-first 400k size profile: PASS')
