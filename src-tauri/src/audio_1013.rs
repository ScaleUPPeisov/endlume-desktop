use crate::model::QueueJob;
use serde_json::json;
use std::{path::{Path,PathBuf},sync::{Arc,atomic::{AtomicBool,Ordering}}};
use tauri::{AppHandle,Emitter,Manager};
use tauri_plugin_shell::ShellExt;

const CANCELLED:&str="__ENDLUME_CANCELLED__";
const GROUP_WIDTH:usize=4;

pub(crate) struct PreparedAudio1013{
  pub job:QueueJob,
  pub work_dir:PathBuf,
}

fn processing_requested(job:&QueueJob)->bool{
  job.settings.crossfade_sec>0.01||job.settings.normalize_lufs||job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false)
}

fn is_mp3(path:&str)->bool{Path::new(path).extension().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("mp3")).unwrap_or(false)}

fn eligible(job:&QueueJob)->bool{
  if !cfg!(target_os="windows"){return false}
  if job.project.audio.is_empty(){return false}
  let has_non_mp3=job.project.audio.iter().any(|x|!is_mp3(x));
  has_non_mp3&&(job.project.audio.len()>=8||processing_requested(job))
}

fn cancelled(cancel:&AtomicBool)->Result<(),String>{if cancel.load(Ordering::SeqCst){Err(CANCELLED.into())}else{Ok(())}}

pub(crate) fn transition_count_for_tracks(mut count:usize)->usize{
  let mut transitions=0usize;
  while count>1{
    let mut start=0usize;
    let mut next=0usize;
    while start<count{
      let width=(count-start).min(GROUP_WIDTH);
      transitions+=width.saturating_sub(1);
      next+=1;
      start+=width;
    }
    count=next;
  }
  transitions
}

async fn tool_output(app:&AppHandle,name:&str,args:Vec<String>,stage:&str)->Result<Vec<u8>,String>{
  #[cfg(feature="e2e-render")]
  eprintln!("ENDLUME_1013_TOOL_CMD {}",json!({"name":name,"stage":stage,"args":&args}));
  let out=app.shell().sidecar(name).map_err(|e|format!("ENDLUME 10.0.13 {stage}: {name} недоступен: {e}"))?.args(args).output().await.map_err(|e|format!("ENDLUME 10.0.13 {stage}: запуск {name}: {e}"))?;
  if !out.status.success(){
    let raw=String::from_utf8_lossy(&out.stderr).trim().to_string();
    return Err(format!("ENDLUME 10.0.13 {stage}: {name} failed\n{raw}"))
  }
  Ok(out.stdout)
}

async fn probe_duration(app:&AppHandle,path:&Path)->Result<f64,String>{
  let args=vec![
    "-v".into(),"error".into(),"-show_entries".into(),"format=duration".into(),
    "-of".into(),"default=noprint_wrappers=1:nokey=1".into(),path.to_string_lossy().into_owned()
  ];
  let stdout=tool_output(app,"ffprobe",args,"duration probe").await?;
  let raw=String::from_utf8_lossy(&stdout);
  let value=raw.trim().parse::<f64>().map_err(|_|format!("ENDLUME 10.0.13 duration probe: некорректная длительность {}: {}",path.display(),raw.trim()))?;
  if !value.is_finite()||value<=0.0{return Err(format!("ENDLUME 10.0.13 duration probe: пустой/некорректный audio {}",path.display()))}
  Ok(value)
}

async fn normalize_track(app:&AppHandle,input:&Path,out:&Path,cancel:&AtomicBool,index:usize,total:usize)->Result<f64,String>{
  cancelled(cancel)?;
  let duration=probe_duration(app,input).await?;
  let args=vec![
    "-hide_banner".into(),"-loglevel".into(),"error".into(),
    "-i".into(),input.to_string_lossy().into_owned(),"-vn".into(),
    "-af".into(),"aresample=48000:async=1:first_pts=0,aformat=sample_fmts=s32:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB".into(),
    "-c:a".into(),"flac".into(),"-compression_level".into(),"5".into(),
    "-y".into(),out.to_string_lossy().into_owned()
  ];
  tool_output(app,"ffmpeg",args,&format!("normalize WAV {index}/{total}")).await?;
  cancelled(cancel)?;
  if !out.is_file()||std::fs::metadata(out).map(|m|m.len()).unwrap_or(0)<1024{return Err(format!("ENDLUME 10.0.13 normalize WAV {index}/{total}: output missing {}",out.display()))}
  Ok(duration)
}

async fn combine_group(app:&AppHandle,inputs:&[PathBuf],out:&Path,crossfade:f64,cancel:&AtomicBool,stage:&str)->Result<(),String>{
  cancelled(cancel)?;
  if inputs.is_empty(){return Err(format!("ENDLUME 10.0.13 {stage}: empty audio group"))}
  if inputs.len()==1{
    std::fs::copy(&inputs[0],out).map_err(|e|format!("ENDLUME 10.0.13 {stage}: copy {} -> {}: {e}",inputs[0].display(),out.display()))?;
    return Ok(())
  }
  let mut args=vec!["-hide_banner".into(),"-loglevel".into(),"error".into(),"-filter_complex_threads".into(),"2".into()];
  for input in inputs{args.push("-i".into());args.push(input.to_string_lossy().into_owned());}
  let mut graph=String::new();
  let last=if crossfade>0.01{
    let mut cur="0:a".to_string();
    for i in 1..inputs.len(){
      let out_label=format!("xf{i}");
      graph.push_str(&format!("[{cur}][{i}:a]acrossfade=d={crossfade}:c1=tri:c2=tri[{out_label}];"));
      cur=out_label;
    }
    cur
  }else{
    let labels=(0..inputs.len()).map(|i|format!("[{i}:a]")).collect::<String>();
    graph.push_str(&format!("{labels}concat=n={}:v=0:a=1[joined];",inputs.len()));
    "joined".to_string()
  };
  graph.push_str(&format!("[{last}]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=s32:sample_rates=48000:channel_layouts=stereo[outa]"));
  args.push("-filter_complex".into());args.push(graph);
  args.push("-map".into());args.push("[outa]".into());
  args.push("-c:a".into());args.push("flac".into());args.push("-compression_level".into());args.push("5".into());
  args.push("-y".into());args.push(out.to_string_lossy().into_owned());
  tool_output(app,"ffmpeg",args,stage).await?;
  cancelled(cancel)?;
  if !out.is_file()||std::fs::metadata(out).map(|m|m.len()).unwrap_or(0)<1024{return Err(format!("ENDLUME 10.0.13 {stage}: output missing {}",out.display()))}
  Ok(())
}

async fn bounded_assemble(app:&AppHandle,tracks:Vec<PathBuf>,work:&Path,crossfade:f64,cancel:&AtomicBool)->Result<PathBuf,String>{
  let mut current=tracks;
  let mut round=0usize;
  while current.len()>1{
    round+=1;
    let mut next=Vec::with_capacity((current.len()+GROUP_WIDTH-1)/GROUP_WIDTH);
    for (group_index,group) in current.chunks(GROUP_WIDTH).enumerate(){
      cancelled(cancel)?;
      let out=work.join(format!("assemble-r{round:02}-g{group_index:02}.flac"));
      combine_group(app,group,&out,crossfade,cancel,&format!("bounded crossfade round {round} group {}",group_index+1)).await?;
      next.push(out);
    }
    if round>1{
      for old in current{if old.starts_with(work)&&old.file_name().and_then(|x|x.to_str()).map(|x|x.starts_with("assemble-r")).unwrap_or(false){let _=std::fs::remove_file(old);}}
    }
    current=next;
  }
  current.into_iter().next().ok_or_else(||"ENDLUME 10.0.13 bounded audio assembly produced no output".into())
}

async fn finalize_mp3(app:&AppHandle,assembled:&Path,ambient:Option<&str>,normalize_lufs:bool,out:&Path,cancel:&AtomicBool)->Result<(),String>{
  cancelled(cancel)?;
  let mut args=vec!["-hide_banner".into(),"-loglevel".into(),"error".into(),"-i".into(),assembled.to_string_lossy().into_owned()];
  let ambient_enabled=ambient.map(|x|!x.trim().is_empty()).unwrap_or(false);
  if let Some(path)=ambient.filter(|x|!x.trim().is_empty()){
    args.push("-stream_loop".into());args.push("-1".into());args.push("-i".into());args.push(path.into());
  }
  let mut graph=if normalize_lufs{
    "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[music]".to_string()
  }else{
    "[0:a]anull[music]".to_string()
  };
  if ambient_enabled{
    graph.push_str(";[1:a]aresample=48000:async=1:first_pts=0,aformat=sample_rates=48000:channel_layouts=stereo,volume=0.18[amb];[music][amb]amix=inputs=2:duration=first:weights='1 1':normalize=0,alimiter=limit=0.98[outa]");
  }else{
    graph.push_str(";[music]aresample=48000:async=1:first_pts=0,alimiter=limit=0.98[outa]");
  }
  args.push("-filter_complex".into());args.push(graph);args.push("-map".into());args.push("[outa]".into());
  args.push("-c:a".into());args.push("libmp3lame".into());args.push("-b:a".into());args.push("320k".into());args.push("-ar".into());args.push("48000".into());args.push("-ac".into());args.push("2".into());
  args.push("-y".into());args.push(out.to_string_lossy().into_owned());
  tool_output(app,"ffmpeg",args,"bounded final HQ MP3").await?;
  cancelled(cancel)?;
  if !out.is_file()||std::fs::metadata(out).map(|m|m.len()).unwrap_or(0)<1024{return Err(format!("ENDLUME 10.0.13 final audio missing {}",out.display()))}
  let duration=probe_duration(app,out).await?;
  if duration<=0.0{return Err("ENDLUME 10.0.13 final audio duration invalid".into())}
  Ok(())
}

async fn prepare_inner(app:&AppHandle,job:&QueueJob,work:&Path,cancel:&AtomicBool)->Result<QueueJob,String>{
  let total=job.project.audio.len();
  let _=app.emit("render-warning",json!({"id":job.project.id,"message":format!("Windows Audio Safety 10.0.13: готовлю {total} треков bounded-memory pipeline (максимум {GROUP_WIDTH} входа FFmpeg одновременно).") }));
  let normalized_dir=work.join("normalized");
  std::fs::create_dir_all(&normalized_dir).map_err(|e|format!("ENDLUME 10.0.13 audio temp dir: {e}"))?;
  let mut normalized=Vec::with_capacity(total);let mut durations=Vec::with_capacity(total);
  for (i,src) in job.project.audio.iter().enumerate(){
    let input=Path::new(src);
    if !input.is_file(){return Err(format!("ENDLUME 10.0.13 audio source missing: {}",input.display()))}
    let out=normalized_dir.join(format!("track-{i:03}.flac"));
    durations.push(normalize_track(app,input,&out,cancel,i+1,total).await?);
    normalized.push(out);
    if (i+1)%5==0||i+1==total{let _=app.emit("render-warning",json!({"id":job.project.id,"message":format!("Windows Audio Safety: нормализовано {}/{} треков",i+1,total)}));}
  }
  let min_track=durations.iter().copied().fold(f64::INFINITY,f64::min);
  let cf=job.settings.crossfade_sec.clamp(0.0,10.0).min((min_track*0.40).max(0.0));
  let assembled=bounded_assemble(app,normalized,work,cf,cancel).await?;
  let final_mp3=work.join("ENDLUME-1013-bounded-audio.mp3");
  finalize_mp3(app,&assembled,job.ambient.as_deref(),job.settings.normalize_lufs,&final_mp3,cancel).await?;
  let final_duration=probe_duration(app,&final_mp3).await?;
  let expected=(durations.iter().sum::<f64>()-cf*((durations.len().saturating_sub(1)) as f64)).max(0.2);
  let tolerance=(expected*0.002).max(0.35);
  if (final_duration-expected).abs()>tolerance{return Err(format!("ENDLUME 10.0.13 audio duration gate failed: expected={expected:.3}s actual={final_duration:.3}s tolerance={tolerance:.3}s"))}
  let mut prepared=job.clone();
  prepared.project.audio=vec![final_mp3.to_string_lossy().into_owned()];
  prepared.settings.crossfade_sec=0.0;
  prepared.settings.normalize_lufs=false;
  prepared.ambient=None;
  let _=app.emit("engine-profile",json!({"id":job.project.id,"audioBounded1013":true,"sourceTracks":total,"maxSimultaneousInputs":GROUP_WIDTH,"transitionCount":transition_count_for_tracks(total),"crossfadeApplied":cf,"normalizeApplied":job.settings.normalize_lufs,"ambientApplied":job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false),"expectedAudioDuration":expected,"actualAudioDuration":final_duration,"preparedAudio":final_mp3}));
  Ok(prepared)
}

pub(crate) async fn prepare_windows_bounded_audio(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<Option<PreparedAudio1013>,String>{
  if !eligible(job){return Ok(None)}
  cancelled(cancel.as_ref())?;
  let root=app.path().app_cache_dir().map_err(|e|format!("ENDLUME 10.0.13 app cache: {e}"))?.join("audio-1013-bounded");
  std::fs::create_dir_all(&root).map_err(|e|format!("ENDLUME 10.0.13 audio cache root: {e}"))?;
  let work=root.join(uuid::Uuid::new_v4().to_string());
  std::fs::create_dir_all(&work).map_err(|e|format!("ENDLUME 10.0.13 audio work dir: {e}"))?;
  match prepare_inner(app,job,&work,cancel.as_ref()).await{
    Ok(prepared)=>Ok(Some(PreparedAudio1013{job:prepared,work_dir:work})),
    Err(e)=>{let _=std::fs::remove_dir_all(&work);Err(e)}
  }
}

pub(crate) fn cleanup_prepared_audio(prepared:&PreparedAudio1013){let _=std::fs::remove_dir_all(&prepared.work_dir);}

#[cfg(test)]
mod tests{
  use super::*;
  use crate::model::{ProjectScanItem,RenderSettings};

  fn job(audio:Vec<String>,crossfade:f64,normalize_lufs:bool)->QueueJob{
    QueueJob{
      project:ProjectScanItem{id:"x".into(),name:"x".into(),path:"x".into(),media:vec!["x.png".into()],audio,valid:true,error:None,anchors:None},
      settings:RenderSettings{width:1920,height:1080,fps:60,codec:"h265".into(),bitrate_mbps:4.0,duration_hours:2.0,duration_mode:"whole-track".into(),loop_mode:"none".into(),crossfade_sec:crossfade,normalize_lufs,output_dir:"x".into(),preset:"x".into(),encoder_preference:"auto".into()},
      effects:vec![],subscribes:vec![],ambient:None
    }
  }

  #[test]
  fn bounded_width_is_four(){assert_eq!(GROUP_WIDTH,4)}

  #[test]
  fn transition_count_matches_actual_hierarchy(){
    for (tracks,expected) in [(1,0),(2,1),(4,3),(5,4),(8,7),(20,19),(30,29)]{
      assert_eq!(transition_count_for_tracks(tracks),expected,"tracks={tracks}");
    }
  }

  #[test]
  fn non_mp3_many_tracks_are_targeted(){
    let j=job((0..20).map(|i|format!("{i}.wav")).collect(),10.0,false);
    if cfg!(target_os="windows"){assert!(eligible(&j))}else{assert!(!eligible(&j))}
  }

  #[test]
  fn compatible_mp3s_keep_existing_path(){
    let j=job((0..20).map(|i|format!("{i}.mp3")).collect(),10.0,true);
    assert!(!eligible(&j));
  }
}