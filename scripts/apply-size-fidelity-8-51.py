#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()

def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.51 profile: missing {rel}')
    return p

def must(cond,msg):
    if not cond: raise SystemExit('8.51 profile: '+msg)

p=need('src-tauri/src/render.rs')
s=p.read_text(encoding='utf-8')

# 8.51 must keep the proven 8.50 production encoder contract: Apple Silicon
# VideoToolbox q100/500k first, libx265 CRF18/500k only as fallback. The later
# x265-first/400k experiment caused the physical full-project speed regression.
good_choose='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  if encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  "libx265".into()
}'''
bad_choose='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  if attempt==1&&encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  if encoder_works(app,"libx265").await{return "libx265".into()}
  "libx265".into()
}'''
must(good_choose in s or bad_choose in s,'active encoder selector not found')
if bad_choose in s:
    s=s.replace(bad_choose,good_choose,1)

# Restore the software fallback ceiling too; it is not the normal M1 path, but
# fallback must preserve the same 500k production budget instead of a hidden 400k variant.
s=s.replace('"-crf","18","-maxrate","400k","-bufsize","4M"','"-crf","18","-maxrate","500k","-bufsize","4M"',1)
s=s.replace('fn hybrid_video_kbps(_s:&RenderSettings)->u64{400}','fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',1)
s=s.replace('RENDER_CACHE_GENERATION:&str="8.51-x265-crf18-size400-v2"','RENDER_CACHE_GENERATION:&str="8.50-speed-quality-q100-v1"',1)
s=s.replace('8.51 encoder={} quality_first=true final_faststart=false target_video_kbps=400 size_target_mb=500-700 vt_q100_fallback=true','8.51 encoder={} hardware_first=true final_faststart=false target_video_kbps=500 q100=true manifest_speed=true',1)

for marker in [
    'attempt==1&&encoder_works(app,"hevc_videotoolbox")',
    '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"',
    '"-crf","18","-maxrate","500k","-bufsize","4M"',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    'RENDER_CACHE_GENERATION:&str="8.50-speed-quality-q100-v1"',
    'VISUAL_PLAN_CACHE_GENERATION:&str="8.51-manifest-v1"',
    'let idx=i%durations.len();',
    'let duration_mode=if smart_repeat_project(job){"whole-track"}else{job.settings.duration_mode.as_str()};',
    'FFMPEG_STALL_TIMEOUT_SECS:u64=120',
]: must(marker in s,'postcondition missing: '+marker)

a=s.find('async fn choose_hybrid_encoder')
b=s.find('async fn probe_audio_decodes',a)
must(a>=0 and b>a,'choose_hybrid_encoder scope not found')
sel=s[a:b]
must('attempt==1&&encoder_works(app,"hevc_videotoolbox")' in sel,'VideoToolbox is not hardware-first')
must('attempt==1&&encoder_works(app,"libx265")' not in sel,'x265-first regression survived')
must('if t-target<=240.0{t}else{target}' not in s,'legacy song-cut cap returned')

p.write_text(s,encoding='utf-8')
print('ENDLUME 8.51 VideoToolbox q100 hardware-first 500k production profile: PASS')
