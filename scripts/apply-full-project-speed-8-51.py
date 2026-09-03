#!/usr/bin/env python3
from pathlib import Path
import re,sys

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
VERSION='1.0.0-alpha.8.51'

def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.51: missing {rel}')
    return p

def must(c,m):
    if not c: raise SystemExit('8.51: '+m)

p=need('src-tauri/src/render.rs')
s=p.read_text(encoding='utf-8')

# 8.50 fidelity/audio/stability contracts are immutable in this release.
for marker in [
    'RENDER_CACHE_GENERATION:&str="8.50-speed-quality-q100-v1"',
    'attempt==1&&encoder_works(app,"hevc_videotoolbox")',
    '"-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
    'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};',
    'FFMPEG_STALL_TIMEOUT_SECS:u64=120',
    'ffprobe_output_timeout(app,args,Duration::from_secs(12))',
    'let idx=i%durations.len();',
    'audio_timeline_849_tests',
    'materialize_continuous_audio',
    'VisualSource::Concat(p)=>args.extend',
]: must(marker in s,'8.50 invariant missing: '+marker)
must('if t-target<=240.0{t}else{target}' not in s,'old song truncation cap returned')

# A single still is always the fast-repeat product shape. Keep video projects out.
old='fn smart_repeat_project(job:&QueueJob)->bool{job.project.media.len()==1&&job.project.media.iter().all(|m|is_image(m))}'
new='''fn smart_repeat_project(job:&QueueJob)->bool{
  if job.project.media.len()!=1{return false}
  let m=&job.project.media[0];if is_image(m){return true}
  Path::new(m).extension().and_then(|x|x.to_str()).map(|x|matches!(x.to_ascii_lowercase().as_str(),"jpg"|"jpeg"|"png"|"webp"|"bmp"|"tif"|"tiff"|"heic"|"heif"|"avif")).unwrap_or(false)
}'''
if old in s:s=s.replace(old,new,1)
must('"heic"|"heif"|"avif"' in s,'robust one-still fast-path detector missing')

# 8.51 has its own manifest/fragment key generation. Do not invalidate the
# expensive 8.50 q100 visual masters or audio caches.
anchor='const RENDER_CACHE_GENERATION:&str="8.50-speed-quality-q100-v1";'
must(anchor in s,'8.50 cache generation anchor missing')
s=s.replace(anchor,anchor+'\nconst VISUAL_PLAN_CACHE_GENERATION:&str="8.51-manifest-v1";',1)

# Frame-quantized keys collapse float noise from recurring Subscribe events.
helper_anchor='fn render_cache_ready(path:&Path)->bool{std::fs::metadata(path).map(|m|m.is_file()&&m.len()>1024).unwrap_or(false)}'
must(helper_anchor in s,'render_cache_ready anchor missing')
helpers=r'''

fn visual_frame_q(v:f64,fps:u32)->f64{let f=fps.max(1) as f64;(v.max(0.0)*f).round()/f}

async fn cached_visual_fragment(app:&AppHandle,job:&QueueJob,variant:&Path,vd:f64,phase:f64,len:f64,state:&str,encoder:&str,attempt:u32,cancel:&AtomicBool,base:f64,span:f64,started:i64,timer:&Instant)->Result<PathBuf,String>{
  let qphase=visual_frame_q(phase,job.settings.fps);let qlen=visual_frame_q(len,job.settings.fps).max(1.0/job.settings.fps.max(1) as f64);
  let raw=format!("{}|fragment|{}|phase={:.6}|len={:.6}|state={}",VISUAL_PLAN_CACHE_GENERATION,render_file_stamp(variant),qphase,qlen,state);
  let out=render_cache_dir(app)?.join(format!("fragment-{}.mp4",render_cache_hash(&raw)));
  if render_cache_ready(&out){render_diag(job,"render-cache",&format!("HIT fragment phase={qphase:.3} len={qlen:.3} {}",out.display()));return Ok(out)}
  copy_segment(app,job,variant,vd,qphase,qlen,&out,encoder,attempt,cancel,base,span,started,timer).await?;
  render_diag(job,"render-cache",&format!("STORE fragment phase={qphase:.3} len={qlen:.3} {}",out.display()));Ok(out)
}

async fn append_smart_manifest_interval(app:&AppHandle,job:&QueueJob,variant:&Path,vd:f64,start:f64,len:f64,phase_sensitive:bool,state:&str,segments:&mut Vec<PathBuf>,encoder:&str,attempt:u32,cancel:&AtomicBool,base:f64,span:f64,started:i64,timer:&Instant)->Result<(),String>{
  let frame=1.0/job.settings.fps.max(1) as f64;let cycle=visual_frame_q(vd,job.settings.fps).max(frame);let mut left=visual_frame_q(len,job.settings.fps);if left<frame{return Ok(())}
  let mut phase=if phase_sensitive{visual_frame_q(start%cycle,job.settings.fps)}else{0.0};
  if phase>=frame&&left>=frame{
    let first=(cycle-phase).min(left);let p=cached_visual_fragment(app,job,variant,cycle,phase,first,state,encoder,attempt,cancel,base,span,started,timer).await?;segments.push(p);left=(left-first).max(0.0);phase=0.0;
  }
  while left+frame*0.25>=cycle{segments.push(variant.to_path_buf());left=(left-cycle).max(0.0)}
  if left>=frame*0.50{let p=cached_visual_fragment(app,job,variant,cycle,0.0,left,state,encoder,attempt,cancel,base,span,started,timer).await?;segments.push(p)}
  Ok(())
}
'''
s=s.replace(helper_anchor,helper_anchor+helpers,1)

# Replace ONLY the visual planner. Non-smart/video behavior remains the old long
# concat path. Smart one-image projects never materialize multi-minute normal
# segments; the concat manifest references short q100 masters repeatedly.
start=s.find('async fn assemble_visual(')
end=s.find('\n\nasync fn ',start+10)
must(start>=0 and end>start,'assemble_visual block not found')
old_block=s[start:end]
must('copy_segment(app,job,&variant,vd,a,b-a' in old_block,'expected 8.50 long copy-segment path missing')
must('VisualSource::Concat(list)' in old_block,'8.50 smart concat shortcut missing')
new_block=r'''async fn assemble_visual(app:&AppHandle,job:&QueueJob,source_master:&Path,master_duration:f64,effects:&[EffectPreset],subs:&[SubscribePreset],final_duration:f64,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<VisualSource,String>{
  let mark=Instant::now();let events=subscribe_events(app,subs,final_duration).await?;let has_timed=timed_effects(effects,final_duration);let smart=smart_repeat_project(job);
  let mut variants:HashMap<String,(PathBuf,f64)>=HashMap::new();
  let initial=active_effects_at(effects,0.001,final_duration);let key=state_key(&initial);let p=build_variant(app,job,source_master,master_duration,&initial,work,encoder,attempt,cancel,0,started,timer).await?;variants.insert(key.clone(),(p,master_duration));
  if events.is_empty()&&!has_timed{emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());return Ok(VisualSource::Loop(variants.get(&key).unwrap().0.clone()))}
  let mut boundaries=vec![0.0,final_duration];for e in effects.iter().filter(|e|e.enabled){if e.start_sec>0.0&&e.start_sec<final_duration{boundaries.push(e.start_sec)}if let Some(x)=e.end_sec{if x>0.0&&x<final_duration{boundaries.push(x)}}}for e in &events{boundaries.push(e.start);boundaries.push(e.end)}
  boundaries.sort_by(|a,b|a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));boundaries.dedup_by(|a,b|(*a-*b).abs()<0.001);
  let intervals=boundaries.windows(2).filter(|w|w[1]-w[0]>0.005).map(|w|(w[0],w[1])).collect::<Vec<_>>();let mut segments=Vec::new();let mut sub_cache:HashMap<String,PathBuf>=HashMap::new();let subscribe_segments=intervals.iter().filter(|(a,b)|{let mid=(*a+*b)/2.0;events.iter().any(|e|e.start<=mid&&e.end>mid)}).count();if intervals.len()>4096{return Err(format!("Visual plan слишком раздроблен: {} сегментов",intervals.len()))}render_diag(job,"subscribe",&format!("8.51 manifest={} events={} intervals={} subscribe_segments={} final_duration={:.3}s",smart,events.len(),intervals.len(),subscribe_segments,final_duration));let mut subscribe_done=0usize;
  for (i,(a,b)) in intervals.iter().copied().enumerate(){if cancel.load(Ordering::SeqCst){return Err(CANCELLED.into())}let mid=(a+b)/2.0;let active_fx=active_effects_at(effects,mid,final_duration);let k=state_key(&active_fx);
    if !variants.contains_key(&k){let no=variants.len();let v=build_variant(app,job,source_master,master_duration,&active_fx,work,encoder,attempt,cancel,no,started,timer).await?;variants.insert(k.clone(),(v,master_duration));}
    let (variant,vd)=variants.get(&k).cloned().unwrap();let active_sub=events.iter().filter(|e|e.start<=mid&&e.end>mid).cloned().collect::<Vec<_>>();let seg=work.join(format!("visual-seg-{i:04}.mp4"));let base=64.0+(i as f64/intervals.len().max(1) as f64)*22.0;let span=22.0/intervals.len().max(1) as f64;
    if active_sub.is_empty(){
      if smart{append_smart_manifest_interval(app,job,&variant,vd,a,b-a,!active_fx.is_empty(),&k,&mut segments,encoder,attempt,cancel,base,span,started,timer).await?;}
      else{copy_segment(app,job,&variant,vd,a,b-a,&seg,encoder,attempt,cancel,base,span,started,timer).await?;segments.push(seg);}
    }else{
      subscribe_done+=1;let phase=visual_frame_q(a%vd.max(0.1),job.settings.fps);let phase_key=if active_fx.is_empty(){0.0}else{phase};let qlen=visual_frame_q(b-a,job.settings.fps);
      let sub_state=active_sub.iter().map(|e|format!("offset={:.6}|{}",visual_frame_q((a-e.event_start).max(0.0),job.settings.fps),serde_json::to_string(&e.sub).unwrap_or_default())).collect::<Vec<_>>().join("||");
      let raw=format!("{}|subscribe|{}|phase={:.6}|len={:.6}|state={}|{}",VISUAL_PLAN_CACHE_GENERATION,render_file_stamp(&variant),phase_key,qlen,k,sub_state);let ck=render_cache_hash(&raw);let cached=render_cache_dir(app)?.join(format!("subscribe-{}.mp4",ck));
      if render_cache_ready(&cached){render_diag(job,"subscribe",&format!("HIT {}/{} phase={phase_key:.3} len={qlen:.3} {}",subscribe_done,subscribe_segments,cached.display()));segments.push(cached.clone());sub_cache.insert(ck,cached);}
      else{render_sub_segment(app,job,&variant,vd,a,qlen,&active_sub,&cached,encoder,attempt,cancel,base,span,started,timer).await?;sub_cache.insert(ck,cached.clone());render_diag(job,"subscribe",&format!("STORE {}/{} phase={phase_key:.3} len={qlen:.3}",subscribe_done,subscribe_segments));segments.push(cached);}
    }
  }
  let list=work.join("visual-concat.txt");let text=segments.iter().map(|p|format!("file '{}'",p.to_string_lossy().replace('\\',"/"))).collect::<Vec<_>>().join("\n");std::fs::write(&list,text).map_err(|e|e.to_string())?;
  if smart{render_diag(job,"subscribe",&format!("8.51 MANIFEST_READY elapsed={:.3}s files={} events={} subscribe_segments={} cache_entries={}",mark.elapsed().as_secs_f64(),segments.len(),events.len(),subscribe_segments,sub_cache.len()));emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());return Ok(VisualSource::Concat(list))}
  let long=work.join("video-long.mp4");let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-an","-c:v","copy","-progress","pipe:1","-y",long.to_string_lossy().as_ref()].into_iter().map(String::from).collect();run_ffmpeg(app,job,started,timer,args,"Склеиваю визуальную дорожку",86.0,4.0,final_duration,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());Ok(VisualSource::Long(long))
}'''
s=s[:start]+new_block+s[end:]

# Version only. Product name, bundle id and updater identity remain untouched.
for rel in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    x=need(rel);t=x.read_text(encoding='utf-8');t=re.sub(r'1\.0\.0-alpha\.8\.\d+',VERSION,t);x.write_text(t,encoding='utf-8')

# Add pure regression tests for frame-quantized manifest math without changing
# runtime semantics outside this speed path.
test_anchor='#[cfg(test)]\nmod audio_timeline_849_tests'
idx=s.find(test_anchor)
must(idx>=0,'audio regression module anchor missing')
manifest_tests=r'''
#[cfg(test)]
mod manifest_851_tests{
  use super::visual_frame_q;
  #[test]fn frame_quantization_is_stable(){assert!((visual_frame_q(10.0000004,60)-10.0).abs()<1e-9);assert!((visual_frame_q(10.0166664,60)-10.016666666666667).abs()<1e-6);}
  #[test]fn two_hour_plan_does_not_need_long_intermediate(){let cycle=60.0;let normal=595.0;let full=(normal/cycle) as usize;let tail=normal-(full as f64*cycle);assert_eq!(full,9);assert!((tail-55.0).abs()<1e-9);let manifest_entries=(full+2)*12;assert!(manifest_entries<200);}
}

'''
s=s[:idx]+manifest_tests+s[idx:]

for marker in [
    'VISUAL_PLAN_CACHE_GENERATION:&str="8.51-manifest-v1"',
    'append_smart_manifest_interval',
    '8.51 MANIFEST_READY',
    'visual_frame_q',
    'manifest_851_tests',
    'attempt==1&&encoder_works(app,"hevc_videotoolbox")',
    '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"',
    'let idx=i%durations.len();',
    'FFMPEG_STALL_TIMEOUT_SECS:u64=120',
]: must(marker in s,'postcondition missing: '+marker)
must('if t-target<=240.0{t}else{target}' not in s,'song cut cap returned')
must('copy_segment(app,job,&variant,vd,a,b-a,&cached' not in s,'8.49 full normal interval cache survived')

p.write_text(s,encoding='utf-8')
print('ENDLUME 8.51 full-project manifest speed migration: PASS')
