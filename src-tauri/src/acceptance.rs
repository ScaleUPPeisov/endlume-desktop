use crate::{model::QueueJob,render};
use serde_json::{json,Value};
use std::{collections::HashSet,fs,path::{Path,PathBuf},sync::{Arc,atomic::AtomicBool},time::{Instant,SystemTime}};
use tauri::AppHandle;
use tauri_plugin_shell::ShellExt;

async fn sidecar(app:&AppHandle,name:&str,args:Vec<String>)->Result<(bool,String,String),String>{
  let out=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  Ok((out.status.success(),String::from_utf8_lossy(&out.stdout).into_owned(),String::from_utf8_lossy(&out.stderr).into_owned()))
}

fn mp4_files(dir:&Path)->HashSet<PathBuf>{
  fs::read_dir(dir).ok().into_iter().flatten().flatten().map(|e|e.path()).filter(|p|p.extension().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("mp4")).unwrap_or(false)).collect()
}

fn newest(paths:impl Iterator<Item=PathBuf>)->Option<PathBuf>{
  paths.max_by_key(|p|fs::metadata(p).and_then(|m|m.modified()).unwrap_or(SystemTime::UNIX_EPOCH))
}

async fn duration(app:&AppHandle,path:&Path)->Result<f64,String>{
  let args=vec![
    "-v".into(),"error".into(),"-show_entries".into(),"format=duration".into(),"-of".into(),"default=nw=1:nk=1".into(),path.to_string_lossy().into_owned()
  ];
  let (_,stdout,stderr)=sidecar(app,"ffprobe",args).await?;
  stdout.trim().parse::<f64>().map_err(|_|format!("ffprobe duration failed for {}: {}",path.display(),stderr.trim()))
}

async fn probe(app:&AppHandle,path:&Path)->Result<Value,String>{
  let args=vec![
    "-v".into(),"error".into(),"-show_streams".into(),"-show_format".into(),"-of".into(),"json".into(),path.to_string_lossy().into_owned()
  ];
  let (ok,stdout,stderr)=sidecar(app,"ffprobe",args).await?;
  if !ok{return Err(format!("ffprobe failed: {}",stderr.trim()))}
  serde_json::from_str(&stdout).map_err(|e|e.to_string())
}

async fn full_decode(app:&AppHandle,path:&Path)->Result<Value,String>{
  let started=Instant::now();
  let args=vec![
    "-hide_banner".into(),"-v".into(),"error".into(),"-i".into(),path.to_string_lossy().into_owned(),"-f".into(),"null".into(),"-".into()
  ];
  let (ok,_stdout,stderr)=sidecar(app,"ffmpeg",args).await?;
  Ok(json!({"ok":ok && stderr.trim().is_empty(),"seconds":started.elapsed().as_secs_f64(),"stderr":stderr.trim()}))
}

async fn seek_checks(app:&AppHandle,path:&Path,total:f64)->Result<Vec<Value>,String>{
  let mut rows=Vec::new();
  for fraction in [0.10_f64,0.25,0.50,0.75,0.90,0.99]{
    let at=(total*fraction).max(0.0);
    let started=Instant::now();
    let args=vec![
      "-hide_banner".into(),"-v".into(),"error".into(),"-ss".into(),format!("{at:.6}"),"-i".into(),path.to_string_lossy().into_owned(),"-t".into(),"0.5".into(),"-map".into(),"0:v:0".into(),"-map".into(),"0:a:0?".into(),"-f".into(),"null".into(),"-".into()
    ];
    let (ok,_stdout,stderr)=sidecar(app,"ffmpeg",args).await?;
    rows.push(json!({"fraction":fraction,"at":at,"ok":ok && stderr.trim().is_empty(),"seconds":started.elapsed().as_secs_f64(),"stderr":stderr.trim()}));
  }
  Ok(rows)
}

async fn run_inner(app:&AppHandle)->Result<Value,String>{
  let job_path=std::env::var("ENDLUME_ACCEPTANCE_JOB").map_err(|_|"ENDLUME_ACCEPTANCE_JOB is not set".to_string())?;
  let raw=fs::read_to_string(&job_path).map_err(|e|format!("read job: {e}"))?;
  let job:QueueJob=serde_json::from_str(&raw).map_err(|e|format!("parse job: {e}"))?;
  let out_dir=PathBuf::from(&job.settings.output_dir);
  fs::create_dir_all(&out_dir).map_err(|e|e.to_string())?;
  let before=mp4_files(&out_dir);

  let mut input_durations=Vec::new();
  for p in &job.project.audio{
    let d=duration(app,Path::new(p)).await?;
    input_durations.push(json!({"path":p,"duration":d}));
  }
  let input_total=input_durations.iter().filter_map(|v|v.get("duration").and_then(|x|x.as_f64())).sum::<f64>();

  let export_started=Instant::now();
  render::render_job(app,&job,Arc::new(AtomicBool::new(false))).await?;
  let export_seconds=export_started.elapsed().as_secs_f64();

  let after=mp4_files(&out_dir);
  let created=after.difference(&before).cloned().collect::<Vec<_>>();
  let result=newest(created.into_iter()).or_else(||newest(after.into_iter())).ok_or("render succeeded but output mp4 was not found")?;
  let bytes=fs::metadata(&result).map_err(|e|e.to_string())?.len();
  let metadata=probe(app,&result).await?;
  let output_duration=metadata.get("format").and_then(|v|v.get("duration")).and_then(|v|v.as_str()).and_then(|v|v.parse::<f64>().ok()).unwrap_or(0.0);
  let decode=full_decode(app,&result).await?;
  let seeks=seek_checks(app,&result,output_duration).await?;

  Ok(json!({
    "source_head":std::env::var("ENDLUME_SOURCE_HEAD").unwrap_or_default(),
    "platform":std::env::consts::OS,
    "arch":std::env::consts::ARCH,
    "project_id":job.project.id,
    "track_count":job.project.audio.len(),
    "input_audio_duration":input_total,
    "input_tracks":input_durations,
    "export_seconds":export_seconds,
    "output_path":result,
    "output_bytes":bytes,
    "output_duration":output_duration,
    "probe":metadata,
    "full_decode":decode,
    "seek_checks":seeks
  }))
}

pub async fn run(app:AppHandle){
  let receipt=std::env::var("ENDLUME_ACCEPTANCE_RECEIPT").unwrap_or_else(|_|"/tmp/endlume-acceptance.json".into());
  let (payload,code)=match run_inner(&app).await{
    Ok(v)=>(json!({"status":"ok","result":v}),0),
    Err(e)=>(json!({"status":"error","error":e}),2)
  };
  if let Ok(text)=serde_json::to_string_pretty(&payload){let _=fs::write(&receipt,format!("{text}\n"));}
  app.exit(code);
}
