#!/usr/bin/env python3
from pathlib import Path
import re,sys

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
VERSION='1.0.0-alpha.8.52'
VIDEO_KBPS=360


def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.52: missing {rel}')
    return p

def must(cond,msg):
    if not cond: raise SystemExit('8.52: '+msg)

def fn_scope(text,name):
    m=re.search(r'(?m)^(?:pub\s+)?async\s+fn\s+'+re.escape(name)+r'\s*\(',text)
    if not m: m=re.search(r'(?m)^fn\s+'+re.escape(name)+r'\s*\(',text)
    must(m is not None,f'{name} not found')
    start=m.start(); opening=text.find('{',m.end()); must(opening>=0,f'{name} opening brace missing')
    depth=0;i=opening;n=len(text);state='code';block=0;raw_hashes=0
    while i<n:
        c=text[i]; nxt=text[i+1] if i+1<n else ''
        if state=='line':
            if c=='\n': state='code'
            i+=1; continue
        if state=='block':
            if c=='/' and nxt=='*': block+=1;i+=2;continue
            if c=='*' and nxt=='/':
                block-=1;i+=2
                if block==0: state='code'
                continue
            i+=1;continue
        if state=='string':
            if c=='\\': i+=2;continue
            if c=='"': state='code'
            i+=1;continue
        if state=='raw':
            if c=='"' and text.startswith('#'*raw_hashes,i+1): i+=1+raw_hashes;state='code';continue
            i+=1;continue
        if c=='/' and nxt=='/': state='line';i+=2;continue
        if c=='/' and nxt=='*': state='block';block=1;i+=2;continue
        if c=='"': state='string';i+=1;continue
        if c=='r':
            j=i+1;h=0
            while j<n and text[j]=='#': h+=1;j+=1
            if j<n and text[j]=='"': state='raw';raw_hashes=h;i=j+1;continue
        if c=='{': depth+=1
        elif c=='}':
            depth-=1
            if depth==0:return start,i+1
        i+=1
    must(False,f'{name} closing brace missing')

p=need('src-tauri/src/render.rs')
s=p.read_text(encoding='utf-8')

for marker in [
    'VISUAL_PLAN_CACHE_GENERATION:&str="8.51-manifest-v1"',
    'RENDER_CACHE_GENERATION:&str="8.50-speed-quality-q100-v1"',
    'attempt==1&&encoder_works(app,"hevc_videotoolbox")',
    '"-crf","18","-maxrate","500k","-bufsize","4M"',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
    'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};',
    'let duration_mode=if smart_repeat_project(job){"whole-track"}else{job.settings.duration_mode.as_str()};',
    '8.51 MANIFEST_READY',
]: must(marker in s,'8.51 invariant missing before patch: '+marker)

# ---------------------------------------------------------------------------
# 1. Size bug: Effects and Subscribe currently bypass Hybrid Fidelity and call
# encoder_args(..., false), which obeys the generic UI Mbps value. For one-image
# projects this is the direct cause of multi-GB outputs. Use a dedicated CRF18
# long-GOP composite profile instead; non-smart/video projects remain untouched.
# ---------------------------------------------------------------------------
helper_anchor='async fn build_variant('
idx=s.find(helper_anchor);must(idx>=0,'build_variant anchor missing')
helper=f'''fn smart_composite_encoder_args(job:&QueueJob,encoder:&str,duration:f64)->Vec<String>{{
  if !smart_repeat_project(job){{return encoder_args(encoder,&job.settings,false)}}
  let frames=(job.settings.fps.max(1) as f64*duration.max(1.0)).round().max(1.0) as u32;let g=frames.to_string();
  if encoder=="libx265"{{
    let x265=format!("keyint={{}}:min-keyint={{}}:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0:pools=2:frame-threads=2",g,g);
    vec!["-c:v","libx265","-preset","ultrafast","-crf","18","-maxrate","{VIDEO_KBPS}k","-bufsize","4M","-x265-params",&x265,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }}else{{
    vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-b:v","{VIDEO_KBPS}k","-maxrate","700k","-bufsize","8M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }}
}}

'''
s=s[:idx]+helper+s[idx:]

bs,be=fn_scope(s,'build_variant');block=s[bs:be]
must('args.extend(encoder_args(encoder,&job.settings,false));' in block,'build_variant still not using generic encoder_args as expected')
block=block.replace('args.extend(encoder_args(encoder,&job.settings,false));','args.extend(smart_composite_encoder_args(job,encoder,master_duration));',1)
s=s[:bs]+block+s[be:]

rs,re_=fn_scope(s,'render_sub_segment');block=s[rs:re_]
must('args.extend(encoder_args(encoder,&job.settings,false));' in block,'render_sub_segment generic encoder_args call missing')
block=block.replace('args.extend(encoder_args(encoder,&job.settings,false));','args.extend(smart_composite_encoder_args(job,encoder,len));',1)
s=s[:rs]+block+s[re_:]

# All smart one-image pieces must use the same HEVC implementation/extradata.
# Restore the proven CRF18 x265-first selector from 8.49. VideoToolbox remains
# fallback for encoder failure, but is no longer the normal Effects path.
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
must(old_choose in s,'8.51 hardware-first hybrid selector missing')
s=s.replace(old_choose,new_choose,1)

# Tighten only the smart x265 master budget. CRF18, 4M I-frame buffer and long
# GOP are preserved, so image fidelity remains protected while average payload
# targets ~500-700 MB for 2h-class videos with normal 192-320k audio.
s=s.replace('"-crf","18","-maxrate","500k","-bufsize","4M"',f'"-crf","18","-maxrate","{VIDEO_KBPS}k","-bufsize","4M"',1)
s=s.replace('fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',f'fn hybrid_video_kbps(_s:&RenderSettings)->u64{{{VIDEO_KBPS}}}',1)

# New visual bytes must never reuse 8.50/8.51 caches.
s=s.replace('RENDER_CACHE_GENERATION:&str="8.50-speed-quality-q100-v1"','RENDER_CACHE_GENERATION:&str="8.52-crf18-size360-v1"',1)
s=s.replace('VISUAL_PLAN_CACHE_GENERATION:&str="8.51-manifest-v1"','VISUAL_PLAN_CACHE_GENERATION:&str="8.52-parallel-composite-v1"',1)

# ---------------------------------------------------------------------------
# 2. Speed bug: cache-miss Subscribe segments are independent but 8.51 awaits
# each one serially. Collect exact phase/state jobs first and render up to four
# at once. No phase normalization, no timing changes, no removed Effects.
# ---------------------------------------------------------------------------
as_,ae=fn_scope(s,'assemble_visual');block=s[as_:ae]
needle='let intervals=boundaries.windows(2).filter(|w|w[1]-w[0]>0.005).map(|w|(w[0],w[1])).collect::<Vec<_>>();let mut segments=Vec::new();let mut sub_cache:HashMap<String,PathBuf>=HashMap::new();'
must(needle in block,'8.51 interval planner declaration changed')
replacement=needle+'let mut pending_sub:Vec<(PathBuf,f64,f64,f64,Vec<SubEvent>,PathBuf,f64,f64)>=Vec::new();'
block=block.replace(needle,replacement,1)
old_miss='else{render_sub_segment(app,job,&variant,vd,a,qlen,&active_sub,&cached,encoder,attempt,cancel,base,span,started,timer).await?;sub_cache.insert(ck,cached.clone());render_diag(job,"subscribe",&format!("STORE {}/{} phase={phase_key:.3} len={qlen:.3}",subscribe_done,subscribe_segments));segments.push(cached);}'
new_miss='else{pending_sub.push((variant.clone(),vd,a,qlen,active_sub.clone(),cached.clone(),base,span));sub_cache.insert(ck,cached.clone());render_diag(job,"subscribe",&format!("QUEUE {}/{} phase={phase_key:.3} len={qlen:.3}",subscribe_done,subscribe_segments));segments.push(cached);}'
must(old_miss in block,'8.51 serial Subscribe miss branch not found')
block=block.replace(old_miss,new_miss,1)
list_anchor='  let list=work.join("visual-concat.txt");'
must(list_anchor in block,'visual concat list anchor missing')
parallel=r'''  if !pending_sub.is_empty(){
    let parallel_mark=Instant::now();render_diag(job,"subscribe",&format!("8.52 PARALLEL_START misses={} lanes=4",pending_sub.len()));
    for chunk in pending_sub.chunks(4){
      match chunk.len(){
        4=>{let a=&chunk[0];let b=&chunk[1];let c=&chunk[2];let d=&chunk[3];let (ra,rb,rc,rd)=tokio::join!(
          render_sub_segment(app,job,a.0.as_path(),a.1,a.2,a.3,&a.4,a.5.as_path(),encoder,attempt,cancel,a.6,a.7,started,timer),
          render_sub_segment(app,job,b.0.as_path(),b.1,b.2,b.3,&b.4,b.5.as_path(),encoder,attempt,cancel,b.6,b.7,started,timer),
          render_sub_segment(app,job,c.0.as_path(),c.1,c.2,c.3,&c.4,c.5.as_path(),encoder,attempt,cancel,c.6,c.7,started,timer),
          render_sub_segment(app,job,d.0.as_path(),d.1,d.2,d.3,&d.4,d.5.as_path(),encoder,attempt,cancel,d.6,d.7,started,timer));ra?;rb?;rc?;rd?;},
        3=>{let a=&chunk[0];let b=&chunk[1];let c=&chunk[2];let (ra,rb,rc)=tokio::join!(
          render_sub_segment(app,job,a.0.as_path(),a.1,a.2,a.3,&a.4,a.5.as_path(),encoder,attempt,cancel,a.6,a.7,started,timer),
          render_sub_segment(app,job,b.0.as_path(),b.1,b.2,b.3,&b.4,b.5.as_path(),encoder,attempt,cancel,b.6,b.7,started,timer),
          render_sub_segment(app,job,c.0.as_path(),c.1,c.2,c.3,&c.4,c.5.as_path(),encoder,attempt,cancel,c.6,c.7,started,timer));ra?;rb?;rc?;},
        2=>{let a=&chunk[0];let b=&chunk[1];let (ra,rb)=tokio::join!(
          render_sub_segment(app,job,a.0.as_path(),a.1,a.2,a.3,&a.4,a.5.as_path(),encoder,attempt,cancel,a.6,a.7,started,timer),
          render_sub_segment(app,job,b.0.as_path(),b.1,b.2,b.3,&b.4,b.5.as_path(),encoder,attempt,cancel,b.6,b.7,started,timer));ra?;rb?;},
        1=>{let a=&chunk[0];render_sub_segment(app,job,a.0.as_path(),a.1,a.2,a.3,&a.4,a.5.as_path(),encoder,attempt,cancel,a.6,a.7,started,timer).await?;},
        _=>{}
      }
    }
    render_diag(job,"subscribe",&format!("8.52 PARALLEL_READY misses={} elapsed={:.3}s",pending_sub.len(),parallel_mark.elapsed().as_secs_f64()));
  }
'''
block=block.replace(list_anchor,parallel+list_anchor,1)
block=block.replace('8.51 MANIFEST_READY','8.52 MANIFEST_READY')
s=s[:as_]+block+s[ae:]

# tokio::join! requires macros. Tauri already supplies the runtime; enable only
# the direct features used by this module.
p.write_text(s,encoding='utf-8')

c=need('src-tauri/Cargo.toml');ct=c.read_text(encoding='utf-8')
ct=ct.replace('tokio = { version = "1", features = ["time"] }','tokio = { version = "1", features = ["time", "macros", "rt-multi-thread"] }')
c.write_text(ct,encoding='utf-8')

# Version sync only; UI/brand/updater identity remain unchanged.
for rel in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    x=need(rel);t=x.read_text(encoding='utf-8');t=re.sub(r'1\.0\.0-alpha\.8\.\d+',VERSION,t);x.write_text(t,encoding='utf-8')

s=need('src-tauri/src/render.rs').read_text(encoding='utf-8')
for marker in [
    'RENDER_CACHE_GENERATION:&str="8.52-crf18-size360-v1"',
    'VISUAL_PLAN_CACHE_GENERATION:&str="8.52-parallel-composite-v1"',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{360}',
    '"-crf","18","-maxrate","360k","-bufsize","4M"',
    'attempt==1&&encoder_works(app,"libx265")',
    'smart_composite_encoder_args(job,encoder,master_duration)',
    'smart_composite_encoder_args(job,encoder,len)',
    '8.52 PARALLEL_START',
    'tokio::join!',
    '8.52 MANIFEST_READY',
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
    'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};',
    'let duration_mode=if smart_repeat_project(job){"whole-track"}else{job.settings.duration_mode.as_str()};',
]: must(marker in s,'postcondition missing: '+marker)

must('args.extend(encoder_args(encoder,&job.settings,false));' not in s[fn_scope(s,'build_variant')[0]:fn_scope(s,'build_variant')[1]],'build_variant still bypasses smart fidelity')
must('args.extend(encoder_args(encoder,&job.settings,false));' not in s[fn_scope(s,'render_sub_segment')[0]:fn_scope(s,'render_sub_segment')[1]],'Subscribe still bypasses smart fidelity')
print('ENDLUME 8.52 production speed/size migration: PASS')
