#!/usr/bin/env python3
from pathlib import Path
import re, sys
ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
VERSION='1.0.0-alpha.8.47'

def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.47: missing {rel}')
    return p

def must(c,m):
    if not c: raise SystemExit('8.47: '+m)

p=need('src-tauri/src/render.rs'); s=p.read_text(encoding='utf-8')
for marker in [
    'FFMPEG_STALL_TIMEOUT_SECS:u64=120',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
    'resolved_job.settings.codec="h265".into();',
    'ffprobe_output_timeout(app,args,Duration::from_secs(12))',
    '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"',
    'let mut sub_cache:HashMap<String,PathBuf>=HashMap::new();',
]: must(marker in s, '8.46 invariant missing: '+marker)

old='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{\n  if attempt==1&&encoder_works(app,"libx265").await{return "libx265".into()}\n  #[cfg(target_os="macos")]\n  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}\n  "libx265".into()\n}'''
new='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{\n  #[cfg(target_os="macos")]\n  {if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}\n  if encoder_works(app,"libx265").await{return "libx265".into()}\n  #[cfg(target_os="macos")]\n  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}\n  "libx265".into()\n}'''
must(old in s,'choose_hybrid_encoder 8.46 block changed'); s=s.replace(old,new,1)

old='vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-b:v","500k","-maxrate","4M","-bufsize","16M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"]'
new='vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-b:v","500k","-maxrate","4M","-bufsize","16M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"]'
must(old in s,'hybrid VideoToolbox profile missing'); s=s.replace(old,new,1)

old='args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-video_track_timescale","60000","-movflags","+faststart","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));'
new='args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-video_track_timescale","60000","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));'
must(old in s,'final mux +faststart block missing'); s=s.replace(old,new,1)

old='let args=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-fflags","+genpts","-i",cycle.to_string_lossy().as_ref(),"-t",&final_duration.to_string(),"-map","0:a:0","-c:a","copy","-avoid_negative_ts","make_zero","-movflags","+faststart","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();'
new='let args=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-fflags","+genpts","-i",cycle.to_string_lossy().as_ref(),"-t",&final_duration.to_string(),"-map","0:a:0","-c:a","copy","-avoid_negative_ts","make_zero","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();'
if old in s: s=s.replace(old,new,1)

anchor='let smart_repeat=smart_repeat_project(job);let _=std::fs::remove_file(&out);let encoder=if smart_repeat{choose_hybrid_encoder(app,attempt).await}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};'
must(anchor in s,'encoder selection anchor missing')
repl=anchor+'\n    if smart_repeat{render_diag(job,"performance",&format!("8.47 encoder={} hardware_first={} final_faststart=false target_video_kbps=500",encoder,encoder=="hevc_videotoolbox"));}'
s=s.replace(anchor,repl,1)

for marker in [
    'attempt==1&&encoder_works(app,"hevc_videotoolbox")',
    '"-prio_speed","1"',
    'target_video_kbps=500',
    'ffprobe_output_timeout(app,args,Duration::from_secs(12))',
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
]: must(marker in s,'post-patch marker missing: '+marker)
final_line=[ln for ln in s.splitlines() if '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"' in ln]
must(final_line and all('+faststart' not in ln for ln in final_line),'final mux still uses +faststart')
p.write_text(s,encoding='utf-8')

for rel in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    x=need(rel); t=x.read_text(encoding='utf-8'); t=re.sub(r'1\.0\.0-alpha\.8\.\d+',VERSION,t); x.write_text(t,encoding='utf-8')
print('ENDLUME 8.47 M1 hardware-first render performance migration: PASS')
