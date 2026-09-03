#!/usr/bin/env python3
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent.parent
VERSION='1.0.0-alpha.8.46'

def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.46: missing {rel}')
    return p

def must(cond,msg):
    if not cond: raise SystemExit('8.46: '+msg)

p=need('src-tauri/src/render.rs')
s=p.read_text(encoding='utf-8')
for marker in [
    'ffprobe_output_timeout','Duration::from_secs(12)','last_error.starts_with("FINAL_VERIFY:")',
    'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};','fn cfr_output_args(',
    '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}','force_original_aspect_ratio=increase',
    'materialize_continuous_audio','acrossfade=d={cf}:c1=tri:c2=tri'
]: must(marker in s,'8.45/protected invariant missing: '+marker)

# Diagnostics are append-only and live next to the existing project/error logs.
old='use std::{collections::HashMap,path::{Path,PathBuf},sync::{Arc,OnceLock,atomic::{AtomicBool,Ordering}},time::{Duration,Instant}};'
new='use std::{collections::HashMap,fs::OpenOptions,io::Write,path::{Path,PathBuf},sync::{Arc,OnceLock,atomic::{AtomicBool,Ordering}},time::{Duration,Instant}};'
if old in s: s=s.replace(old,new,1)
must('fs::OpenOptions' in s,'diagnostic imports missing')

old='''const CANCELLED:&str="__ENDLUME_CANCELLED__";
static ENCODER_CACHE:OnceLock<parking_lot::Mutex<HashMap<String,String>>>=OnceLock::new();'''
new='''const CANCELLED:&str="__ENDLUME_CANCELLED__";
const HELPER_TIMEOUT_SECS:u64=120;
const FFMPEG_STALL_TIMEOUT_SECS:u64=120;
static ENCODER_CACHE:OnceLock<parking_lot::Mutex<HashMap<String,String>>>=OnceLock::new();'''
must(old in s,'constants marker missing');s=s.replace(old,new,1)

old='''async fn output(app:&AppHandle,name:&str,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{
  let out=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
  Ok((out.stdout,out.stderr))
}'''
new='''async fn output(app:&AppHandle,name:&str,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{
  let command=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args);
  let limit=if name=="ffprobe"{Duration::from_secs(15)}else{Duration::from_secs(HELPER_TIMEOUT_SECS)};
  let out=tokio::time::timeout(limit,command.output()).await.map_err(|_|format!("{name} helper timeout after {:.0}s",limit.as_secs_f64()))?.map_err(|e|e.to_string())?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
  Ok((out.stdout,out.stderr))
}

fn render_diag_path(job:&QueueJob)->PathBuf{let d=PathBuf::from(&job.settings.output_dir).join("logs");let _=std::fs::create_dir_all(&d);d.join(format!("{} — render-diagnostic.log",safe_name(&job.project.name)))}
fn render_diag(job:&QueueJob,phase:&str,msg:&str){if let Ok(mut f)=OpenOptions::new().create(true).append(true).open(render_diag_path(job)){let _=writeln!(f,"{} [render][{}][{}] {}",chrono::Utc::now().to_rfc3339(),job.project.id,phase,msg);}}
fn render_phase(stage:&str)->&'static str{if stage.contains("Subscribe"){"subscribe"}else if stage.contains("итог")||stage.contains("итоговое"){"final-mux"}else if stage.contains("аудио")||stage.contains("Кроссфейд"){"audio"}else if stage.contains("визуал")||stage.contains("master"){"visual"}else{"ffmpeg"}}
fn ffmpeg_is_stalled(progress_idle:Duration)->bool{progress_idle>=Duration::from_secs(FFMPEG_STALL_TIMEOUT_SECS)}
fn staged_output(args:&[String])->(Vec<String>,Option<(PathBuf,PathBuf)>){let mut a=args.to_vec();let Some(last)=a.last().cloned() else{return(a,None)};if last=="-"||last.starts_with("pipe:"){return(a,None)}let final_path=PathBuf::from(last);let Some(ext)=final_path.extension().and_then(|x|x.to_str()) else{return(a,None)};let Some(stem)=final_path.file_stem().and_then(|x|x.to_str()) else{return(a,None)};let partial=final_path.parent().unwrap_or(Path::new(".")).join(format!("{stem}.partial.{ext}"));let _=std::fs::remove_file(&partial);let n=a.len();a[n-1]=partial.to_string_lossy().into_owned();(a,Some((partial,final_path)))}
fn cleanup_partial(staged:&Option<(PathBuf,PathBuf)>){if let Some((p,_))=staged{let _=std::fs::remove_file(p);}}
fn promote_partial(staged:&Option<(PathBuf,PathBuf)>)->Result<(),String>{let Some((partial,final_path))=staged else{return Ok(())};if !partial.is_file(){return Err(format!("FFmpeg exit=0, но partial-файл отсутствует: {}",partial.display()))}#[cfg(target_os="windows")]if final_path.exists(){let _=std::fs::remove_file(final_path);}std::fs::rename(partial,final_path).map_err(|e|format!("Не удалось завершить файл {}: {e}",final_path.display()))}
async fn stop_child(pid:u32,child:&mut Option<tauri_plugin_shell::process::CommandChild>){#[cfg(unix)]{let _=std::process::Command::new("/bin/kill").arg("-TERM").arg(pid.to_string()).status();tokio::time::sleep(Duration::from_millis(500)).await;}if let Some(c)=child.take(){let _=c.kill();}}
'''
must(old in s,'output helper marker missing');s=s.replace(old,new,1)

start=s.find('async fn run_ffmpeg(app:&AppHandle')
end=s.find('\n\nfn cfr_output_args(',start)
if end<0: end=s.find('\n\nfn base_filter(',start)
must(start>=0 and end>start,'run_ffmpeg block missing')
runner=r'''async fn run_ffmpeg_once(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,args:Vec<String>,stage:&str,base:f64,span:f64,expected_sec:f64,encoder:&str,attempt:u32,cancel:&AtomicBool,stage_attempt:u32)->Result<(),String>{
  emit_progress(app,job,started,timer,base,stage,encoder,attempt,None);
  let (run_args,staged)=staged_output(&args);cleanup_partial(&staged);
  let (mut rx,child)=app.shell().sidecar("ffmpeg").map_err(|e|e.to_string())?.args(run_args.clone()).spawn().map_err(|e|e.to_string())?;
  let pid=child.pid();let phase=render_phase(stage);let proc_started=Instant::now();render_diag(job,phase,&format!("START pid={pid} stage_attempt={stage_attempt}/2 expected={expected_sec:.3}s args={}",run_args.join(" ")));
  let mut child=Some(child);let mut last=base;let mut stderr_tail=String::new();let mut sys=System::new_all();let mut metric_tick=Instant::now();let mut log_tick=Instant::now();let mut last_progress=Instant::now();let mut last_out=0f64;let mut last_frame=0u64;let mut last_size=0u64;
  loop{
    if cancel.load(Ordering::SeqCst){stop_child(pid,&mut child).await;cleanup_partial(&staged);render_diag(job,phase,&format!("CANCEL pid={pid}"));return Err(CANCELLED.into())}
    if ffmpeg_is_stalled(last_progress.elapsed()){let idle=last_progress.elapsed().as_secs_f64();render_diag(job,phase,&format!("STALL pid={pid} no_progress={idle:.1}s last_out_time={:.3}s frame={last_frame} total_size={last_size} killing process",last_out/1_000_000.0));stop_child(pid,&mut child).await;cleanup_partial(&staged);return Err(format!("FFMPEG_STALL: stage={stage}; pid={pid}; no_progress={idle:.1}s; last_out_time={:.3}s; frame={last_frame}; total_size={last_size}",last_out/1_000_000.0))}
    let event=tokio::time::timeout(Duration::from_millis(160),rx.recv()).await;
    if metric_tick.elapsed()>=Duration::from_millis(480){let pids=[Pid::from_u32(pid)];sys.refresh_processes(ProcessesToUpdate::Some(&pids),true);sys.refresh_memory();if let Some(p)=sys.process(pids[0]){let cpu=(p.cpu_usage()/(sys.cpus().len().max(1) as f32)).clamp(0.0,100.0);emit_progress(app,job,started,timer,last,stage,encoder,attempt,Some((cpu,p.memory(),sys.total_memory(),sys.available_memory())))}metric_tick=Instant::now();}
    let ev=match event{Err(_)=>continue,Ok(Some(ev))=>ev,Ok(None)=>{stop_child(pid,&mut child).await;cleanup_partial(&staged);return Err(format!("FFmpeg закрыл канал без статуса завершения: pid={pid}, stage={stage}"))}};
    match ev{
      CommandEvent::Stdout(bytes)|CommandEvent::Stderr(bytes)=>{let text=String::from_utf8_lossy(&bytes);stderr_tail.push_str(&text);if stderr_tail.len()>12000{stderr_tail=stderr_tail.split_off(stderr_tail.len()-9000)}let mut advanced=false;for line in text.lines(){if let Some(v)=line.strip_prefix("out_time_us=").or_else(||line.strip_prefix("out_time_ms=")).and_then(|x|x.parse::<f64>().ok()){if v>last_out{last_out=v;advanced=true}let out_sec=v/1_000_000.0;let frac=if expected_sec>0.0{(out_sec/expected_sec).clamp(0.0,1.0)}else{0.0};let p=base+frac*span;if p-last>=0.01{last=p;emit_progress(app,job,started,timer,p,stage,encoder,attempt,None)}}else if let Some(v)=line.strip_prefix("frame=").and_then(|x|x.trim().parse::<u64>().ok()){if v>last_frame{last_frame=v;advanced=true}}else if let Some(v)=line.strip_prefix("total_size=").and_then(|x|x.trim().parse::<u64>().ok()){if v>last_size{last_size=v;advanced=true}}}if advanced{last_progress=Instant::now()}if log_tick.elapsed()>=Duration::from_secs(5){render_diag(job,phase,&format!("PROGRESS pid={pid} out_time={:.3}s frame={last_frame} total_size={last_size} last_progress={:.2}s ago",last_out/1_000_000.0,last_progress.elapsed().as_secs_f64()));log_tick=Instant::now();}},
      CommandEvent::Error(e)=>{stop_child(pid,&mut child).await;cleanup_partial(&staged);render_diag(job,phase,&format!("ERROR pid={pid} {e}"));return Err(e)},
      CommandEvent::Terminated(t)=>{child.take();let code=t.code.unwrap_or(1);if code!=0{cleanup_partial(&staged);let detail=if stderr_tail.trim().is_empty(){format!("FFmpeg завершился с кодом {:?}",t.code)}else{stderr_tail.lines().rev().take(12).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\n")};render_diag(job,phase,&format!("FAIL pid={pid} exit={code} elapsed={:.2}s",proc_started.elapsed().as_secs_f64()));return Err(detail)}promote_partial(&staged)?;render_diag(job,phase,&format!("SUCCESS pid={pid} exit=0 out_time={:.3}s frame={last_frame} total_size={last_size} elapsed={:.2}s",last_out/1_000_000.0,proc_started.elapsed().as_secs_f64()));break},_=>{}
    }
  }
  emit_progress(app,job,started,timer,base+span,stage,encoder,attempt,None);Ok(())
}
async fn run_ffmpeg(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,args:Vec<String>,stage:&str,base:f64,span:f64,expected_sec:f64,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(),String>{for stage_attempt in 1..=2{match run_ffmpeg_once(app,job,started,timer,args.clone(),stage,base,span,expected_sec,encoder,attempt,cancel,stage_attempt).await{Ok(())=>return Ok(()),Err(e) if e.starts_with("FFMPEG_STALL:")&&stage_attempt==1=>{render_diag(job,render_phase(stage),&format!("RETRY_AFTER_STALL reason={e}"));tokio::time::sleep(Duration::from_millis(350)).await;},Err(e)=>return Err(e)}}Err(format!("FFMPEG_STALL: stage={stage}; controlled retry exhausted"))}'''
s=s[:start]+runner+s[end:]

# Subscribe planning/segment diagnostics and pathological schedule guard.
old='''async fn subscribe_events(app:&AppHandle,subs:&[SubscribePreset],final_duration:f64)->Vec<SubEvent>{
  let mut events=Vec::new();'''
new='''async fn subscribe_events(app:&AppHandle,subs:&[SubscribePreset],final_duration:f64)->Result<Vec<SubEvent>,String>{
  let mut events=Vec::new();'''
must(old in s,'subscribe_events signature missing');s=s.replace(old,new,1)
s=s.replace('if starts.len()>10000{break}','if starts.len()>2048{return Err(format!("Subscribe расписание слишком плотное: более 2048 событий для {}",s.effect.name))}',1)
s=s.replace('for start in starts{events.push(SubEvent{start,end:(start+d).min(final_duration),sub:s.clone(),event_start:start});}','for start in starts{events.push(SubEvent{start,end:(start+d).min(final_duration),sub:s.clone(),event_start:start});if events.len()>2048{return Err("Subscribe: более 2048 событий — остановлено до создания тысяч FFmpeg сегментов".into())}}',1)
s=s.replace('events.sort_by(|a,b|a.start.partial_cmp(&b.start).unwrap_or(std::cmp::Ordering::Equal));events\n}','events.sort_by(|a,b|a.start.partial_cmp(&b.start).unwrap_or(std::cmp::Ordering::Equal));Ok(events)\n}',1)
s=s.replace('let mark=Instant::now();let events=subscribe_events(app,subs,final_duration).await;let has_timed=','let mark=Instant::now();let events=subscribe_events(app,subs,final_duration).await?;let has_timed=',1)
must('subscribe_events(app,subs,final_duration).await?' in s,'subscribe planning errors not propagated')
needle='let intervals=boundaries.windows(2).filter(|w|w[1]-w[0]>0.005).map(|w|(w[0],w[1])).collect::<Vec<_>>();let mut segments=Vec::new();'
must(needle in s,'interval plan marker missing')
insert=needle+'if intervals.len()>4096{return Err(format!("Visual plan слишком раздроблен: {} сегментов",intervals.len()))}let subscribe_segments=intervals.iter().filter(|(a,b)|{let mid=(*a+*b)/2.0;events.iter().any(|e|e.start<=mid&&e.end>mid)}).count();render_diag(job,"subscribe",&format!("events={} intervals={} segments={} final_duration={:.3}s",events.len(),intervals.len(),subscribe_segments,final_duration));let mut subscribe_done=0usize;'
s=s.replace(needle,insert,1)
old='''if active_sub.is_empty(){copy_segment(app,job,&variant,vd,a,b-a,&seg,encoder,attempt,cancel,base,span,started,timer).await?;}else{render_sub_segment(app,job,&variant,vd,a,b-a,&active_sub,&seg,encoder,attempt,cancel,base,span,started,timer).await?;}segments.push(seg);'''
new='''if active_sub.is_empty(){copy_segment(app,job,&variant,vd,a,b-a,&seg,encoder,attempt,cancel,base,span,started,timer).await?;}else{subscribe_done+=1;render_diag(job,"subscribe",&format!("segment {}/{} interval={}/{} start={:.3} duration={:.3} active={}",subscribe_done,subscribe_segments,i+1,intervals.len(),a,b-a,active_sub.len()));render_sub_segment(app,job,&variant,vd,a,b-a,&active_sub,&seg,encoder,attempt,cancel,base,span,started,timer).await?;render_diag(job,"subscribe",&format!("completed {}/{} start={:.3} duration={:.3}",subscribe_done,subscribe_segments,a,b-a));}segments.push(seg);'''
must(old in s,'segment branch missing');s=s.replace(old,new,1)

# Job-level profile and stall must never fall through to the old full-project retry.
anchor='pub async fn render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<(),String>{\n'
must(anchor in s,'render_job marker missing')
s=s.replace(anchor,anchor+'  render_diag(job,"job",&format!("START projectId={} media={} audio={} fps={} resolution={}x{} effects={} subscribe={} engine_preference={}",job.project.id,job.project.media.len(),job.project.audio.len(),job.settings.fps,job.settings.width,job.settings.height,job.effects.iter().filter(|e|e.enabled).count(),job.subscribes.iter().filter(|x|x.effect.enabled).count(),job.settings.encoder_preference));\n',1)
marker='if last_error.starts_with("FINAL_VERIFY:"){return Err(last_error.trim_start_matches("FINAL_VERIFY: ").to_string())}'
must(marker in s,'8.45 final verify retry guard missing')
s=s.replace(marker,marker+'if last_error.starts_with("FFMPEG_STALL:"){return Err(last_error.trim_start_matches("FFMPEG_STALL: ").to_string())}',1)

# Unit guard for stall semantics.
if 'mod watchdog_tests' not in s:
    s+='''\n\n#[cfg(test)]\nmod watchdog_tests{use super::*;#[test]fn active_progress_is_not_stalled(){assert!(!ffmpeg_is_stalled(Duration::from_secs(119)));}#[test]fn stalled_progress_is_detected(){assert!(ffmpeg_is_stalled(Duration::from_secs(120)));assert!(ffmpeg_is_stalled(Duration::from_secs(300)));}}\n'''

for marker in ['FFMPEG_STALL_TIMEOUT_SECS:u64=120','RETRY_AFTER_STALL','staged_output(&args)','promote_partial(&staged)','events={} intervals={} segments={} final_duration','segment {}/{} interval={}/{}','last_error.starts_with("FFMPEG_STALL:")','mod watchdog_tests']:
    must(marker in s,'stability marker missing: '+marker)
for marker in ['ffprobe_output_timeout','Duration::from_secs(12)','resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};','fn cfr_output_args(','"-c:v","copy","-c:a","copy","-video_track_timescale","60000"','fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}','force_original_aspect_ratio=increase','materialize_continuous_audio','acrossfade=d={cf}:c1=tri:c2=tri']:
    must(marker in s,'protected invariant changed: '+marker)
p.write_text(s,encoding='utf-8')

# Effects/Subscribe cache: bounded process, progress-aware stall, partial -> atomic rename.
p=need('src-tauri/src/cache.rs');c=p.read_text(encoding='utf-8')
must('minterpolate=fps={fps}:mi_mode=mci' in c,'motion cache missing');must('"-fps_mode","cfr","-r",fps_s.as_str()' in c,'CFR cache missing')
c=c.replace('use std::{fs,path::{Path,PathBuf},time::UNIX_EPOCH};','use std::{fs,path::{Path,PathBuf},time::{Duration,Instant,UNIX_EPOCH}};',1)
c=c.replace('use tauri_plugin_shell::ShellExt;','use tauri_plugin_shell::{process::CommandEvent,ShellExt};',1)
marker='pub async fn prepare(app:&AppHandle,e:&EffectPreset,fps:u32)->Result<EffectPreset,String>{'
must(marker in c,'cache prepare marker missing')
helper=r'''async fn run_cache_ffmpeg(app:&AppHandle,e:&EffectPreset,args:Vec<String>,partial:&Path,final_path:&Path)->Result<(),String>{let _=fs::remove_file(partial);let (mut rx,child)=app.shell().sidecar("ffmpeg").map_err(|x|format!("Не найден встроенный FFmpeg: {x}"))?.args(args).spawn().map_err(|x|format!("Не удалось запустить FFmpeg для Effects: {x}"))?;let pid=child.pid();let mut child=Some(child);let mut last=Instant::now();let mut out=0f64;let mut frame=0u64;let mut size=0u64;let mut stderr=String::new();loop{if last.elapsed()>=Duration::from_secs(120){if let Some(ch)=child.take(){let _=ch.kill();}let _=fs::remove_file(partial);return Err(format!("Effects/Subscribe cache stall: '{}' pid={} no progress {:.1}s",e.name,pid,last.elapsed().as_secs_f64()))}let ev=match tokio::time::timeout(Duration::from_millis(200),rx.recv()).await{Err(_)=>continue,Ok(Some(v))=>v,Ok(None)=>{if let Some(ch)=child.take(){let _=ch.kill();}let _=fs::remove_file(partial);return Err(format!("Effects/Subscribe cache закрыл канал без статуса: '{}'",e.name))}};match ev{CommandEvent::Stdout(b)|CommandEvent::Stderr(b)=>{let text=String::from_utf8_lossy(&b);stderr.push_str(&text);if stderr.len()>9000{stderr=stderr.split_off(stderr.len()-7000)}let mut changed=false;for line in text.lines(){if let Some(v)=line.strip_prefix("out_time_us=").or_else(||line.strip_prefix("out_time_ms=")).and_then(|x|x.parse::<f64>().ok()){if v>out{out=v;changed=true}}else if let Some(v)=line.strip_prefix("frame=").and_then(|x|x.trim().parse::<u64>().ok()){if v>frame{frame=v;changed=true}}else if let Some(v)=line.strip_prefix("total_size=").and_then(|x|x.trim().parse::<u64>().ok()){if v>size{size=v;changed=true}}}if changed{last=Instant::now()}},CommandEvent::Error(err)=>{if let Some(ch)=child.take(){let _=ch.kill();}let _=fs::remove_file(partial);return Err(err)},CommandEvent::Terminated(t)=>{child.take();if t.code.unwrap_or(1)!=0{let _=fs::remove_file(partial);return Err(format!("Не удалось подготовить кэш '{}': {}",e.name,stderr.trim()))}break},_=>{}}}if !partial.is_file(){return Err(format!("Кэш '{}' завершился без partial-файла",e.name))}#[cfg(target_os="windows")]if final_path.exists(){let _=fs::remove_file(final_path);}fs::rename(partial,final_path).map_err(|x|format!("Не удалось завершить кэш '{}': {x}",e.name))}

'''
if 'async fn run_cache_ffmpeg(' not in c:c=c.replace(marker,helper+marker,1)
old='''    let args=vec!["-hide_banner","-loglevel","error","-i",e.source.as_str(),"-vf",vf.as_str(),"-an","-c:v","qtrle","-pix_fmt",pix,"-fps_mode","cfr","-r",fps_s.as_str(),"-video_track_timescale","60000","-y",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();
    let out=app.shell().sidecar("ffmpeg").map_err(|x|format!("Не найден встроенный FFmpeg: {x}"))?.args(args).output().await.map_err(|x|format!("Не удалось запустить FFmpeg для Effects: {x}"))?;
    if !out.status.success(){return Err(format!("Не удалось подготовить кэш '{}': {}",e.name,String::from_utf8_lossy(&out.stderr).trim()))}
'''
new='''    let partial=path.with_file_name(format!("{}.partial.mov",path.file_stem().and_then(|x|x.to_str()).unwrap_or("effect-cache")));
    let args=vec!["-hide_banner","-loglevel","error","-i",e.source.as_str(),"-vf",vf.as_str(),"-an","-c:v","qtrle","-pix_fmt",pix,"-fps_mode","cfr","-r",fps_s.as_str(),"-video_track_timescale","60000","-progress","pipe:1","-y",partial.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();
    run_cache_ffmpeg(app,e,args,&partial,&path).await?;
'''
must(old in c,'direct cache output block missing');c=c.replace(old,new,1)
must('.args(args).output().await' not in c,'unbounded cache output survived');must('.partial.mov' in c and 'Duration::from_secs(120)' in c,'cache partial/watchdog missing')
p.write_text(c,encoding='utf-8')

# Friendly queue error for a controlled stall.
p=need('src-tauri/src/queue.rs');q=p.read_text(encoding='utf-8')
needle='  if raw=="__ENDLUME_CANCELLED__"{return "Остановлено пользователем".into()}\n'
if 'FFmpeg остановлен watchdog' not in q:
    must(needle in q,'queue friendly error marker missing');q=q.replace(needle,needle+'  if raw.contains("no_progress=")||raw.to_lowercase().contains("ffmpeg_stall"){return "FFmpeg остановлен watchdog: процесс перестал выдавать реальный прогресс. Partial-файл очищен; очередь продолжит работу.".into()}\n',1)
p.write_text(q,encoding='utf-8')

# Version only; no UI/navigation/updater behavior changes.
for rel in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    x=need(rel);t=x.read_text(encoding='utf-8');t=re.sub(r'1\.0\.0-alpha\.8\.\d+',VERSION,t);x.write_text(t,encoding='utf-8')

print('ENDLUME 8.46 render stability migration: PASS')
