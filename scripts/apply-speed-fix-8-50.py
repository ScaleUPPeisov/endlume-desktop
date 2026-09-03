#!/usr/bin/env python3
from pathlib import Path
import re,sys
ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
VERSION='1.0.0-alpha.8.50'
PRODUCT='ENDLUME STUDIO PEISOV'
def need(rel):
 p=ROOT/rel
 if not p.is_file(): raise SystemExit(f'8.50 missing {rel}')
 return p
def must(c,m):
 if not c: raise SystemExit('8.50: '+m)
p=need('src-tauri/src/render.rs'); s=p.read_text()
for marker in ['RENDER_CACHE_GENERATION:&str="8.49-fidelity-v1"','if t-target<=240.0{t}else{target}','ENDLUME STUDIO PEISOV']:
 if marker=='if t-target<=240.0{t}else{target}': must(marker not in s,'old song truncation returned')
 else: must(marker in s,'8.49 invariant missing: '+marker)
old='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{\n  if attempt==1&&encoder_works(app,"libx265").await{return "libx265".into()}\n  #[cfg(target_os="macos")]\n  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}\n  if encoder_works(app,"libx265").await{return "libx265".into()}\n  "libx265".into()\n}'''
new='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{\n  #[cfg(target_os="macos")]\n  {if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}\n  if encoder_works(app,"libx265").await{return "libx265".into()}\n  #[cfg(target_os="macos")]\n  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}\n  "libx265".into()\n}'''
must(old in s,'8.49 x265-first selector not found'); s=s.replace(old,new,1)
s=s.replace('RENDER_CACHE_GENERATION:&str="8.49-fidelity-v1"','RENDER_CACHE_GENERATION:&str="8.50-hw-fidelity-v1"',1)
oldvt='vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-b:v","500k","-maxrate","4M","-bufsize","16M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"]'
newvt='vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-b:v","500k","-maxrate","12M","-bufsize","48M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"]'
must(oldvt in s,'8.49 VideoToolbox profile not found'); s=s.replace(oldvt,newvt,1)
# Keep the proven CPU x265 profile untouched as fallback only.
for marker in ['"-crf","18","-maxrate","500k","-bufsize","4M"','fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}','resolved_job.settings.width=1920;','resolved_job.settings.height=1080;','FFMPEG_STALL_TIMEOUT_SECS:u64=120','ffprobe_output_timeout(app,args,Duration::from_secs(12))','let idx=i%durations.len();']:
 must(marker in s,'preserved contract missing: '+marker)
p.write_text(s)
for rel in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
 x=need(rel); t=x.read_text(); t=re.sub(r'1\.0\.0-alpha\.8\.\d+',VERSION,t); x.write_text(t)
conf=need('src-tauri/tauri.conf.json').read_text(); must(PRODUCT in conf,'product name changed'); must('studio.endlume.desktop' in conf,'bundle id changed')
print('ENDLUME 8.50 VideoToolbox cold-render speed migration: PASS')
