use crate::{fast_render,model::QueueJob,preview,render};
use serde_json::{json,Value};
use std::{collections::HashSet,fs,path::{Path,PathBuf},sync::{Arc,atomic::AtomicBool},time::{Instant,SystemTime}};
use tauri::{AppHandle,Listener};
use tauri_plugin_shell::ShellExt;

async fn sidecar(app:&AppHandle,name:&str,args:Vec<String>)->Result<(bool,String,String),String>{
  let out=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  Ok((out.status.success(),String::from_utf8_lossy(&out.stdout).into_owned(),String::from_utf8_lossy(&out.stderr).into_owned()))
}
fn mp4_files(dir:&Path)->HashSet<PathBuf>{fs::read_dir(dir).ok().into_iter().flatten().flatten().map(|e|e.path()).filter(|p|p.extension().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("mp4")).unwrap_or(false)).collect()}
fn newest(paths:impl Iterator<Item=PathBuf>)->Option<PathBuf>{paths.max_by_key(|p|fs::metadata(p).and_then(|m|m.modified()).unwrap_or(SystemTime::UNIX_EPOCH))}
async fn duration(app:&AppHandle,path:&Path)->Result<f64,String>{let (_,stdout,stderr)=sidecar(app,"ffprobe",vec!["-v".into(),"error".into(),"-show_entries".into(),"format=duration".into(),"-of".into(),"default=nw=1:nk=1".into(),path.to_string_lossy().into_owned()]).await?;stdout.trim().parse::<f64>().map_err(|_|format!("ffprobe duration failed for {}: {}",path.display(),stderr.trim()))}
async fn probe(app:&AppHandle,path:&Path)->Result<Value,String>{let (ok,stdout,stderr)=sidecar(app,"ffprobe",vec!["-v".into(),"error".into(),"-show_streams".into(),"-show_format".into(),"-of".into(),"json".into(),path.to_string_lossy().into_owned()]).await?;if !ok{return Err(format!("ffprobe failed: {}",stderr.trim()))}serde_json::from_str(&stdout).map_err(|e|e.to_string())}
async fn full_decode(app:&AppHandle,path:&Path)->Result<Value,String>{let started=Instant::now();let (ok,_stdout,stderr)=sidecar(app,"ffmpeg",vec!["-hide_banner".into(),"-v".into(),"error".into(),"-i".into(),path.to_string_lossy().into_owned(),"-f".into(),"null".into(),"-".into()]).await?;Ok(json!({"ok":ok&&stderr.trim().is_empty(),"seconds":started.elapsed().as_secs_f64(),"stderr":stderr.trim()}))}

async fn seek_one(app:&AppHandle,path:&Path,at:f64)->Result<Value,String>{
  let started=Instant::now();let (ok,_stdout,stderr)=sidecar(app,"ffmpeg",vec!["-hide_banner".into(),"-v".into(),"error".into(),"-ss".into(),format!("{at:.6}"),"-i".into(),path.to_string_lossy().into_owned(),"-t".into(),"0.5".into(),"-map".into(),"0:v:0".into(),"-map".into(),"0:a:0?".into(),"-f".into(),"null".into(),"-".into()]).await?;
  Ok(json!({"at":at,"ok":ok&&stderr.trim().is_empty(),"seconds":started.elapsed().as_secs_f64(),"stderr":stderr.trim()}))
}
async fn seek_checks(app:&AppHandle,path:&Path,total:f64)->Result<Vec<Value>,String>{
  let mut points=vec![0.0,total*0.10,total*0.25,total*0.50,total*0.75,total*0.90,total*0.99,1800.0,3600.0,5400.0,7200.0,9000.0];
  for p in &mut points{*p=(*p).max(0.0).min((total-0.25).max(0.0));}
  points.sort_by(|a,b|a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));points.dedup_by(|a,b|(*a-*b).abs()<0.01);
  let mut rows=Vec::with_capacity(points.len());for at in points{rows.push(seek_one(app,path,at).await?);}Ok(rows)
}
fn capture_event(app:&AppHandle,name:&'static str,events:Arc<parking_lot::Mutex<Vec<Value>>>){app.listen(name,move |event|{let payload=serde_json::from_str::<Value>(event.payload()).unwrap_or_else(|_|json!({"raw":event.payload()}));events.lock().push(json!({"event":name,"payload":payload}));});}

async fn preview_evidence(app:&AppHandle,job:&QueueJob)->Result<Vec<Value>,String>{
  let raw=match std::env::var("ENDLUME_ACCEPTANCE_PREVIEW_TIMES"){Ok(v)=>v,Err(_)=>return Ok(Vec::new())};let mut rows=Vec::new();
  for token in raw.split(',').map(str::trim).filter(|s|!s.is_empty()){
    let at=token.parse::<f64>().map_err(|_|format!("invalid preview time: {token}"))?;
    let path=preview::generate_preview(app.clone(),job.project.path.clone(),at,job.effects.clone(),job.subscribes.clone()).await?;
    rows.push(json!({"at":at,"path":path}));
  }
  Ok(rows)
}

async fn run_inner(app:&AppHandle)->Result<Value,String>{
  let job_path=std::env::var("ENDLUME_ACCEPTANCE_JOB").map_err(|_|"ENDLUME_ACCEPTANCE_JOB is not set".to_string())?;let raw=fs::read_to_string(&job_path).map_err(|e|format!("read job: {e}"))?;let job:QueueJob=serde_json::from_str(&raw).map_err(|e|format!("parse job: {e}"))?;let out_dir=PathBuf::from(&job.settings.output_dir);fs::create_dir_all(&out_dir).map_err(|e|e.to_string())?;let before=mp4_files(&out_dir);
  let events=Arc::new(parking_lot::Mutex::new(Vec::<Value>::new()));capture_event(app,"engine-fast-path",events.clone());capture_event(app,"engine-fast-fallback",events.clone());capture_event(app,"engine-timing",events.clone());
  let mut input_durations=Vec::new();for p in &job.project.audio{let d=duration(app,Path::new(p)).await?;input_durations.push(json!({"path":p,"duration":d}));}let input_total=input_durations.iter().filter_map(|v|v.get("duration").and_then(|x|x.as_f64())).sum::<f64>();
  let cancel=Arc::new(AtomicBool::new(false));let export_started=Instant::now();let fast_used=match fast_render::try_render_job(app,&job,cancel.clone()).await?{Some(())=>true,None=>{render::render_job(app,&job,cancel).await?;false}};let export_seconds=export_started.elapsed().as_secs_f64();
  let after=mp4_files(&out_dir);let created=after.difference(&before).cloned().collect::<Vec<_>>();let result=newest(created.into_iter()).or_else(||newest(after.into_iter())).ok_or("render succeeded but output mp4 was not found")?;let bytes=fs::metadata(&result).map_err(|e|e.to_string())?.len();let metadata=probe(app,&result).await?;let output_duration=metadata.get("format").and_then(|v|v.get("duration")).and_then(|v|v.as_str()).and_then(|v|v.parse::<f64>().ok()).unwrap_or(0.0);let decode=full_decode(app,&result).await?;let seeks=seek_checks(app,&result,output_duration).await?;let previews=preview_evidence(app,&job).await?;let captured=events.lock().clone();
  let fallback=captured.iter().rev().find(|e|e.get("event").and_then(Value::as_str)==Some("engine-fast-fallback")).and_then(|e|e.get("payload")).cloned();
  let final_fast=captured.iter().rev().find(|e|e.get("event").and_then(Value::as_str)==Some("engine-fast-path")&&e.get("payload").and_then(|p|p.get("totalMs")).is_some()).and_then(|e|e.get("payload")).cloned();
  Ok(json!({"source_head":std::env::var("ENDLUME_SOURCE_HEAD").unwrap_or_default(),"platform":std::env::consts::OS,"arch":std::env::consts::ARCH,"project_id":job.project.id,"track_count":job.project.audio.len(),"input_audio_duration":input_total,"input_tracks":input_durations,"fast_path_used":fast_used,"legacy_fallback_used":!fast_used,"fallback":fallback,"fast_metrics":final_fast,"events":captured,"export_seconds":export_seconds,"output_path":result,"output_bytes":bytes,"output_duration":output_duration,"probe":metadata,"full_decode":decode,"seek_checks":seeks,"preview_outputs":previews}))
}
pub async fn run(app:AppHandle){let receipt=std::env::var("ENDLUME_ACCEPTANCE_RECEIPT").unwrap_or_else(|_|"/tmp/endlume-acceptance.json".into());let (payload,code)=match run_inner(&app).await{Ok(v)=>(json!({"status":"ok","result":v}),0),Err(e)=>(json!({"status":"error","error":e}),2)};if let Ok(text)=serde_json::to_string_pretty(&payload){let _=fs::write(&receipt,format!("{text}\n"));}app.exit(code);}
