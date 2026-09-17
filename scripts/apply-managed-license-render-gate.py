#!/usr/bin/env python3
from pathlib import Path

p=Path('src-tauri/src/render.rs')
s=p.read_text()
old='''  loop{\n    if cancel.load(Ordering::SeqCst){if let Some(c)=child.take(){let _=c.kill();}return Err(CANCELLED.into())}\n'''
new='''  loop{\n    if crate::license::production_blocked(){if let Some(c)=child.take(){let _=c.kill();}return Err("__ENDLUME_LICENSE_BLOCKED__".into())}\n    if cancel.load(Ordering::SeqCst){if let Some(c)=child.take(){let _=c.kill();}return Err(CANCELLED.into())}\n'''
if new not in s:
    if old not in s: raise SystemExit('run_ffmpeg cancel anchor not found')
    s=s.replace(old,new,1)
old2='''pub async fn render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<(),String>{\n  let mut resolved_job=job.clone();'''
new2='''pub async fn render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<(),String>{\n  if crate::license::production_blocked(){return Err("__ENDLUME_LICENSE_BLOCKED__".into())}\n  let mut resolved_job=job.clone();'''
if new2 not in s:
    if old2 not in s: raise SystemExit('render_job anchor not found')
    s=s.replace(old2,new2,1)
old3='''  let _=app.emit("render-progress",Progress{id:job.project.id.clone(),status:"rendering".into(),progress:progress.clamp(0.0,99.9),stage:stage.into(),started_at:Some(started),elapsed_sec:elapsed,eta_sec:eta,result_path:None,result_bytes:None,actual_video_bitrate:None,cpu_pct:metrics.map(|_|cpu),ram_bytes:metrics.map(|_|ram),ram_total_bytes:metrics.map(|_|total),ram_available_bytes:metrics.map(|_|available),gpu_pct:None,encoder:Some(encoder.into()),attempt:Some(attempt)});\n}'''
new3='''  let _=app.emit("render-progress",Progress{id:job.project.id.clone(),status:"rendering".into(),progress:progress.clamp(0.0,99.9),stage:stage.into(),started_at:Some(started),elapsed_sec:elapsed,eta_sec:eta,result_path:None,result_bytes:None,actual_video_bitrate:None,cpu_pct:metrics.map(|_|cpu),ram_bytes:metrics.map(|_|ram),ram_total_bytes:metrics.map(|_|total),ram_available_bytes:metrics.map(|_|available),gpu_pct:None,encoder:Some(encoder.into()),attempt:Some(attempt)});\n  crate::license::telemetry_render_progress(job,progress.clamp(0.0,99.9),eta,stage,encoder);\n}'''
if new3 not in s:
    if old3 not in s: raise SystemExit('emit_progress anchor not found')
    s=s.replace(old3,new3,1)
p.write_text(s)
print('ENDLUME managed license render gate applied')
