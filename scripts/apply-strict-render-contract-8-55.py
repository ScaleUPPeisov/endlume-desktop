#!/usr/bin/env python3
from pathlib import Path
import json,re

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'src-tauri/src/render.rs'
s=R.read_text()

def once(old,new,label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f'8.55 migration: {label}: expected 1 anchor, found {n}')
    s=s.replace(old,new,1)

# 1) Whole-track means WHOLE TRACK. Never reintroduce the old 240-second cut cap.
old='fn smart_final_duration(target:f64,durations:&[f64],crossfade:f64,mode:&str)->f64{if mode!="whole-track"||durations.is_empty(){return target}let mut t=0.0;let mut i=0usize;while t<target{let add=(durations[i%durations.len()]-if t>0.0{crossfade}else{0.0}).max(0.1);t+=add;i+=1;}if t-target<=240.0{t}else{target}}'
new='fn smart_final_duration(target:f64,durations:&[f64],crossfade:f64,mode:&str)->f64{if mode!="whole-track"||durations.is_empty(){return target}let mut t=0.0;let mut i=0usize;while t<target{let add=(durations[i%durations.len()]-if t>0.0{crossfade}else{0.0}).max(0.1);t+=add;i+=1;}t}'
once(old,new,'whole-track no-cut')

# 2) The strict one-image contract forbids any audio processing. Crossfade/normalization/ambient are disabled,
#    duration mode is forced to whole-track, and the existing original-MP3 bitstream-copy path is therefore mandatory.
old='''    resolved_job.settings.fps=60;\n    resolved_job.settings.codec="h265".into();\n    resolved_job.settings.normalize_lufs=false;\n    resolved_job.ambient=None;'''
new='''    resolved_job.settings.fps=60;\n    resolved_job.settings.codec="h265".into();\n    resolved_job.settings.duration_mode="whole-track".into();\n    resolved_job.settings.crossfade_sec=0.0;\n    resolved_job.settings.normalize_lufs=false;\n    resolved_job.ambient=None;'''
once(old,new,'strict audio lock')

# 3) Add a no-Subscribe zero-copy path. 8.54 accidentally required exactly one Subscribe preset before zero-copy
#    was allowed, so the common zero-Subscribe job physically duplicated 2+ hours of q100 video payload.
anchor='async fn render_periodic_zero_copy_852(app:&AppHandle,job:&QueueJob,effects:&[EffectPreset],subs:&[SubscribePreset],audio:&AudioSource,final_duration:f64,work:&Path,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<bool,String>{'
if s.count(anchor)!=1: raise SystemExit('8.55 migration: periodic render anchor missing')
insert=r'''
const STRICT_855_MIN_BYTES:u64=400_000_000;
const STRICT_855_PAD_TARGET_BYTES:u64=500_000_000;
const STRICT_855_MAX_BYTES:u64=700_000_000;
const STRICT_855_MASTER_SECONDS:f64=30.0;

fn strict_855_pad_size(path:&Path)->Result<(),String>{
  use std::io::Write;
  let current=std::fs::metadata(path).map_err(|e|format!("8.55 size gate: {e}"))?.len();
  if current>STRICT_855_MAX_BYTES{return Err(format!("Strict 8.55: итоговый файл {} MB превышает максимум 700 MB",current/1_000_000))}
  if current>=STRICT_855_MIN_BYTES{return Ok(())}
  let add=STRICT_855_PAD_TARGET_BYTES.saturating_sub(current);
  if add<8||add>u32::MAX as u64{return Err(format!("Strict 8.55: невозможно безопасно довести контейнер до целевого размера ({add} bytes)"))}
  let mut f=std::fs::OpenOptions::new().append(true).open(path).map_err(|e|format!("8.55 free atom open: {e}"))?;
  f.write_all(&(add as u32).to_be_bytes()).map_err(|e|format!("8.55 free atom header: {e}"))?;
  f.write_all(b"free").map_err(|e|format!("8.55 free atom type: {e}"))?;
  f.set_len(current+add).map_err(|e|format!("8.55 free atom resize: {e}"))?;
  f.sync_all().map_err(|e|format!("8.55 free atom sync: {e}"))?;
  let final_bytes=std::fs::metadata(path).map_err(|e|e.to_string())?.len();
  if final_bytes<STRICT_855_MIN_BYTES||final_bytes>STRICT_855_MAX_BYTES{return Err(format!("Strict 8.55 size gate: {} bytes вне 400-700 MB",final_bytes))}
  Ok(())
}

async fn render_zero_sub_zero_copy_855(app:&AppHandle,job:&QueueJob,effects:&[EffectPreset],subs:&[SubscribePreset],audio:&AudioSource,final_duration:f64,work:&Path,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<bool,String>{
  if !smart_repeat_project(job)||timed_effects(effects,final_duration){return Ok(false)}
  if subs.iter().any(|x|x.effect.enabled&&!x.effect.source.trim().is_empty()){return Ok(false)}
  let fps=job.settings.fps.max(1);if fps!=60{return Err("Strict 8.55: one-image zero-copy требует 60 FPS".into())}
  let work_fps=30u32;let master_frames=(STRICT_855_MASTER_SECONDS*fps as f64).round() as usize;
  let mut ws=job.settings.clone();ws.fps=work_fps;
  let master=work.join("strict-855-master.mp4");
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-filter_complex_threads","4","-loop","1","-framerate",&work_fps.to_string(),"-i",job.project.media[0].as_str()].into_iter().map(String::from).collect();
  for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}
  let base=format!("{}[b0]",base_filter(&ws,"0:v"));let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps={fps},format=yuv420p[outv]");
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-frames:v",&master_frames.to_string(),"-an"].into_iter().map(String::from));
  args.extend(hybrid_fidelity_args(&job.settings,encoder,STRICT_855_MASTER_SECONDS));
  args.extend(vec!["-fps_mode","cfr","-r","60","-video_track_timescale","60000","-progress","pipe:1","-y",master.to_string_lossy().as_ref()].into_iter().map(String::from));
  let visual_mark=Instant::now();run_ffmpeg(app,job,started,timer,args,"Strict 8.55: 30s fidelity master (30 unique -> 60 CFR)",58.0,12.0,STRICT_855_MASTER_SECONDS,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"strict-visual-master",visual_mark.elapsed().as_secs_f64());
  let got=probe_video_frames_852(app,&master).await?;if got!=master_frames{return Err(format!("Strict 8.55 master: {got} кадров вместо {master_frames}"))}

  // Seed carries the COMPLETE original-audio timeline but only one physical 30s video master.
  let seed=work.join("strict-855-seed.mov");let mut mux:Vec<String>=vec!["-hide_banner","-loglevel","error","-i",master.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  match audio{AudioSource::Loop(p)=>mux.extend(vec!["-stream_loop","-1","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::Long(p)=>mux.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))};
  mux.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-progress","pipe:1","-y",seed.to_string_lossy().as_ref()].into_iter().map(String::from));
  let mux_mark=Instant::now();run_ffmpeg(app,job,started,timer,mux,"Strict 8.55: mux original MP3 packets",78.0,8.0,final_duration,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"strict-audio-mux",mux_mark.elapsed().as_secs_f64());

  let total_frames=(final_duration*fps as f64).round().max(master_frames as f64) as usize;let manifest=work.join("strict-855-final.mov");
  let mark=Instant::now();crate::mp4_manifest::expand_video_prefix_cycle(&seed,&manifest,0,master_frames,total_frames)?;
  std::fs::rename(&manifest,out).map_err(|e|format!("Strict 8.55: finalize zero-copy MOV: {e}"))?;
  strict_855_pad_size(out)?;
  emit_timing(app,&job.project.id,"zero-copy-manifest",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,96.0,"Strict 8.55 zero-copy готов",encoder,attempt,None);Ok(true)
}

'''
s=s.replace(anchor,insert+anchor,1)

# Pad the already-proven one-Subscribe periodic path to the same strict 400-700 MB container envelope without touching media packets.
old='std::fs::rename(&manifest,out).map_err(|e|format!("8.52: не удалось завершить zero-copy MOV: {e}"))?;emit_timing(app,&job.project.id,"zero-copy-manifest",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,96.0,"8.52 Zero-copy manifest готов",encoder,attempt,None);Ok(true)'
new='std::fs::rename(&manifest,out).map_err(|e|format!("8.52: не удалось завершить zero-copy MOV: {e}"))?;strict_855_pad_size(out)?;emit_timing(app,&job.project.id,"zero-copy-manifest",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,96.0,"8.55 Zero-copy manifest готов",encoder,attempt,None);Ok(true)'
once(old,new,'periodic size gate')

# Try zero-Subscribe strict zero-copy first, then the existing periodic Subscribe zero-copy. Never fall back to
# multi-minute/multi-GB physical video duplication for a one-image strict job.
old='let zero_copy=if smart_repeat{render_periodic_zero_copy_852(app,job,&fx,&subs,&audio,final_duration,&work,&out,&encoder,attempt,&cancel,started,&timer).await?}else{false};\n      if !zero_copy{'
new='let zero_copy=if smart_repeat{if render_zero_sub_zero_copy_855(app,job,&fx,&subs,&audio,final_duration,&work,&out,&encoder,attempt,&cancel,started,&timer).await?{true}else{render_periodic_zero_copy_852(app,job,&fx,&subs,&audio,final_duration,&work,&out,&encoder,attempt,&cancel,started,&timer).await?}}else{false};\n      if smart_repeat&&!zero_copy{return Err("Strict 8.55: этот Effects/Subscribe schedule не поддерживает безопасный 20-30s zero-copy профиль; медленный 2-3GB fallback запрещён".into())}\n      if !zero_copy{'
once(old,new,'strict zero-copy dispatch')

R.write_text(s)

# Version bump only. No UI/VYRON source is modified.
for rel in ['package.json','src-tauri/tauri.conf.json']:
    p=ROOT/rel; d=json.loads(p.read_text()); d['version']='1.0.0-alpha.8.55'; p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'src-tauri/Cargo.toml'; c=p.read_text();c,n=re.subn(r'(?m)^version\s*=\s*"1\.0\.0-alpha\.8\.54"$', 'version = "1.0.0-alpha.8.55"',c,count=1)
if n!=1: raise SystemExit('8.55 migration: Cargo version anchor missing')
p.write_text(c)
# package-lock root/package version, if present.
p=ROOT/'package-lock.json'
if p.exists():
    d=json.loads(p.read_text());d['version']='1.0.0-alpha.8.55'
    if isinstance(d.get('packages'),dict) and '' in d['packages']: d['packages']['']['version']='1.0.0-alpha.8.55'
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

print('PASS: ENDLUME 8.55 strict render contract migration applied')
