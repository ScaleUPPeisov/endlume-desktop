use crate::{model::{EffectPreset,Progress,QueueJob},mp4_manifest,visual_spec};
use serde_json::json;
use std::{fs,path::{Path,PathBuf},sync::{Arc,atomic::{AtomicBool,Ordering}},time::Instant};
use tauri::{AppHandle,Emitter};
use tauri_plugin_shell::ShellExt;

const IMAGE_EXT:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];
const CANCELLED:&str="__ENDLUME_CANCELLED__";

#[derive(Clone)]
struct FastVisualPlan{
  master_seconds:f64,
  cycle_frames:usize,
  effects:Vec<EffectPreset>,
  mode:&'static str,
}

fn is_image(path:&str)->bool{Path::new(path).extension().and_then(|x|x.to_str()).map(|x|IMAGE_EXT.contains(&x.to_ascii_lowercase().as_str())).unwrap_or(false)}
fn is_mp3(path:&str)->bool{Path::new(path).extension().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("mp3")).unwrap_or(false)}
fn safe_name(name:&str)->String{name.chars().map(|c|if ['/', '\\', ':', '*', '?', '"', '<', '>', '|'].contains(&c){'_'}else{c}).collect()}
fn unique_output(dir:&Path,name:&str)->PathBuf{let safe=safe_name(name);let mut p=dir.join(format!("{} — Ready Videos.mp4",safe));let mut n=2;while p.exists(){p=dir.join(format!("{} — Ready Videos_{}.mp4",safe,n));n+=1}p}
fn cancelled(flag:&AtomicBool)->Result<(),String>{if flag.load(Ordering::SeqCst){Err(CANCELLED.into())}else{Ok(())}}

async fn command(app:&AppHandle,name:&str,args:Vec<String>)->Result<Vec<u8>,String>{
  let out=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
  Ok(out.stdout)
}
async fn duration(app:&AppHandle,path:&str)->Result<f64,String>{
  let out=command(app,"ffprobe",vec!["-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",path].into_iter().map(String::from).collect()).await?;
  String::from_utf8_lossy(&out).trim().parse::<f64>().map_err(|_|format!("Не удалось определить длительность: {path}"))
}
async fn video_bitrate(app:&AppHandle,path:&Path)->Option<u64>{
  command(app,"ffprobe",vec!["-v","error","-select_streams","v:0","-show_entries","stream=bit_rate","-of","default=nw=1:nk=1",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await.ok().and_then(|x|String::from_utf8_lossy(&x).trim().parse().ok())
}

fn base_rejection(job:&QueueJob)->Option<String>{
  if !cfg!(target_os="macos"){return Some("fast path is macOS-only".into())}
  if job.project.media.len()!=1||!is_image(&job.project.media[0]){return Some("fast path requires exactly one still image".into())}
  if job.project.audio.is_empty(){return Some("fast path requires audio tracks".into())}
  if !job.project.audio.iter().all(|p|is_mp3(p)){return Some("clean-copy fast path requires MP3 inputs".into())}
  if job.project.audio.iter().any(|p|p.contains('\'')||p.contains('\n')||p.contains('\r')){return Some("unsafe concat-list path; preserve correctness with legacy renderer".into())}
  if !job.settings.codec.eq_ignore_ascii_case("h265"){return Some("fast path currently requires HEVC/H.265".into())}
  if job.settings.fps==0{return Some("invalid FPS".into())}
  if job.settings.crossfade_sec.abs()>=0.0001{return Some("crossfade requires processed audio".into())}
  if job.settings.normalize_lufs{return Some("normalization requires processed audio".into())}
  if job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false){return Some("ambient mix requires processed audio".into())}
  if job.subscribes.iter().any(|s|s.effect.enabled){return Some("Subscribe is absolute-time content and stays on legacy renderer".into())}
  if job.settings.duration_mode!="whole-track"{return Some("fast path currently preserves whole-track mode only".into())}
  None
}

async fn visual_plan(app:&AppHandle,job:&QueueJob)->Result<FastVisualPlan,String>{
  if let Some(reason)=base_rejection(job){return Err(reason)}
  let effects=job.effects.iter().filter(|e|e.enabled).cloned().collect::<Vec<_>>();
  if effects.is_empty(){
    let cycle_frames=(5.0*job.settings.fps as f64).round() as usize;
    return Ok(FastVisualPlan{master_seconds:5.0,cycle_frames,effects,mode:"static-hevc-mp3-packet-copy"})
  }
  for e in &effects{
    if !visual_spec::fast_periodic_effect_supported(e){return Err(format!("effect '{}' is not a proven always-on periodic effect",e.name))}
    if !Path::new(&e.source).is_file(){return Err(format!("effect source not found: {}",e.source))}
  }
  let mut periods=Vec::with_capacity(effects.len());
  for e in &effects{
    let d=duration(app,&e.source).await?;
    let frames=visual_spec::period_frames(d,job.settings.fps).ok_or_else(||format!("effect '{}' duration {d:.6}s is not frame-aligned at {} FPS",e.name,job.settings.fps))?;
    periods.push(frames);
  }
  let common=visual_spec::common_period_frames(&periods,job.settings.fps).ok_or_else(||format!("combined periodic effect cycle is unknown or exceeds {:.0}s",visual_spec::MAX_FAST_COMMON_PERIOD_SEC))?;
  Ok(FastVisualPlan{
    master_seconds:common as f64/job.settings.fps as f64,
    cycle_frames:common as usize,
    effects,
    mode:"periodic-hevc-mp3-packet-copy",
  })
}

fn final_whole_track_duration(target:f64,durations:&[f64])->Option<(f64,usize)>{
  if durations.is_empty(){return None}
  let mut total=0.0;let mut count=0usize;
  while total<target-0.0001{total+=durations[count%durations.len()];count+=1;if count>10000{return None}}
  if total-target>240.0{return None}
  Some((total,count))
}

fn write_side_files(job:&QueueJob,out:&Path,durations:&[f64],track_count:usize)->Result<(),String>{
  let out_dir=out.parent().ok_or("output parent missing")?;
  let stem=out.file_stem().and_then(|x|x.to_str()).unwrap_or(&job.project.name);let safe=safe_name(stem);
  let time_dir=out_dir.join("timecodes");let log_dir=out_dir.join("logs");fs::create_dir_all(&time_dir).map_err(|e|e.to_string())?;fs::create_dir_all(&log_dir).map_err(|e|e.to_string())?;
  let mut t=0.0;let mut tc=String::new();
  for i in 0..track_count{let p=&job.project.audio[i%job.project.audio.len()];let title=Path::new(p).file_stem().and_then(|x|x.to_str()).unwrap_or("Track");let s=t.round() as u64;tc.push_str(&format!("{:02}:{:02}:{:02} {}\n",s/3600,(s%3600)/60,s%60,title));t+=durations[i%durations.len()];}
  fs::write(time_dir.join(format!("{} — timecodes.txt",safe)),tc).map_err(|e|e.to_string())?;
  let list=job.project.audio.iter().enumerate().map(|(i,p)|format!("{}. {}",i+1,Path::new(p).file_name().and_then(|x|x.to_str()).unwrap_or(p))).collect::<Vec<_>>().join("\n");
  fs::write(out_dir.join(format!("{} — tracklist.txt",safe)),list).map_err(|e|e.to_string())?;
  fs::write(log_dir.join(format!("{} — project.json",safe)),serde_json::to_vec_pretty(job).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
  Ok(())
}

async fn verify(app:&AppHandle,out:&Path,expected:f64,job:&QueueJob)->Result<(),String>{
  let d=duration(app,out.to_string_lossy().as_ref()).await?;
  if (d-expected).abs()>0.20{return Err(format!("fast path duration mismatch: {d:.3} vs {expected:.3}"))}
  let raw=command(app,"ffprobe",vec!["-v","error","-show_entries","stream=codec_name,width,height,r_frame_rate,avg_frame_rate","-of","json",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await?;
  let v:serde_json::Value=serde_json::from_slice(&raw).map_err(|e|e.to_string())?;
  let streams=v.get("streams").and_then(|x|x.as_array()).ok_or("ffprobe streams missing")?;
  let video=streams.iter().find(|s|s.get("width").is_some()).ok_or("video stream missing")?;
  streams.iter().find(|s|s.get("codec_name").and_then(|x|x.as_str())==Some("mp3")).ok_or("MP3 stream-copy missing")?;
  if video.get("codec_name").and_then(|x|x.as_str())!=Some("hevc"){return Err("fast path output is not HEVC".into())}
  if video.get("width").and_then(|x|x.as_u64())!=Some(job.settings.width as u64)||video.get("height").and_then(|x|x.as_u64())!=Some(job.settings.height as u64){return Err("fast path resolution mismatch".into())}
  let fps=video.get("avg_frame_rate").and_then(|x|x.as_str()).unwrap_or("");let expected_fps=format!("{}/1",job.settings.fps);
  if fps!=expected_fps{return Err(format!("fast path FPS mismatch: {fps} vs {expected_fps}"))}
  Ok(())
}

async fn encode_master(app:&AppHandle,job:&QueueJob,plan:&FastVisualPlan,master:&Path)->Result<(),String>{
  let fps=job.settings.fps.to_string();let master_len=format!("{:.9}",plan.master_seconds);let g=plan.cycle_frames.to_string();
  let mut args=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",fps.as_str(),"-i",job.project.media[0].as_str()].into_iter().map(String::from).collect::<Vec<_>>();
  for e in &plan.effects{args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}
  let graph=format!("{}[b0]",visual_spec::base_filter("0:v",job.settings.width,job.settings.height,job.settings.fps));
  let (mut graph,last)=visual_spec::apply_effects_filter(graph,"b0".into(),&plan.effects,job.settings.width,job.settings.height,job.settings.fps,1);
  graph.push_str(&format!(";[{last}]format=yuv420p[outv]"));
  args.extend(vec!["-filter_complex",graph.as_str(),"-map","[outv]","-t",master_len.as_str(),"-an","-c:v","hevc_videotoolbox","-realtime","1"].into_iter().map(String::from));
  if plan.effects.is_empty(){args.extend(vec!["-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"].into_iter().map(String::from));}
  else{args.extend(vec!["-q:v","75","-b:v","8M","-maxrate","20M","-bufsize","80M"].into_iter().map(String::from));}
  args.extend(vec!["-g",g.as_str(),"-tag:v","hvc1","-fps_mode","cfr","-r",fps.as_str(),"-video_track_timescale","60000","-y",master.to_string_lossy().as_ref()].into_iter().map(String::from));
  command(app,"ffmpeg",args).await.map(|_|())
}

async fn run_fast(app:&AppHandle,job:&QueueJob,plan:&FastVisualPlan,cancel:&AtomicBool)->Result<(),String>{
  let started_ms=chrono::Utc::now().timestamp_millis();let wall=Instant::now();cancelled(cancel)?;
  let out_dir=PathBuf::from(&job.settings.output_dir);fs::create_dir_all(&out_dir).map_err(|e|e.to_string())?;let out=unique_output(&out_dir,&job.project.name);
  let work=std::env::temp_dir().join(format!("endlume-fast-{}-{}",job.project.id,started_ms));let _=fs::remove_dir_all(&work);fs::create_dir_all(&work).map_err(|e|e.to_string())?;
  let result:Result<(),String>=async{
    let audio_mark=Instant::now();
    let mut durations=Vec::with_capacity(job.project.audio.len());for p in &job.project.audio{durations.push(duration(app,p).await?.max(0.001));}
    let target=job.settings.duration_hours*3600.0;let (final_duration,track_count)=final_whole_track_duration(target,&durations).ok_or("fast path cannot preserve whole-track duration semantics")?;
    let total_frames=(final_duration*job.settings.fps as f64).round() as usize;
    let master=work.join("visual-master.mp4");let seed=work.join("seed.mp4");let list=work.join("audio-concat.txt");
    let mut lines=String::new();for i in 0..track_count{let p=&job.project.audio[i%job.project.audio.len()];lines.push_str(&format!("file '{}'\n",p.replace('\\',"/")));}fs::write(&list,lines).map_err(|e|e.to_string())?;
    let audio_ms=audio_mark.elapsed().as_secs_f64()*1000.0;
    let _=app.emit("engine-timing",json!({"id":job.project.id,"key":"fast-audio-ms","milliseconds":audio_ms}));

    cancelled(cancel)?;let t=Instant::now();encode_master(app,job,plan,&master).await?;let master_ms=t.elapsed().as_secs_f64()*1000.0;
    let _=app.emit("engine-timing",json!({"id":job.project.id,"key":"fast-master-render-ms","milliseconds":master_ms}));

    cancelled(cancel)?;let t=Instant::now();
    command(app,"ffmpeg",vec!["-hide_banner","-loglevel","error","-i",master.to_string_lossy().as_ref(),"-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-video_track_timescale","60000","-y",seed.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await?;
    let mux_ms=t.elapsed().as_secs_f64()*1000.0;let _=app.emit("engine-timing",json!({"id":job.project.id,"key":"fast-mux-ms","milliseconds":mux_ms}));

    cancelled(cancel)?;let t=Instant::now();mp4_manifest::expand_video_prefix_cycle(&seed,&out,0,plan.cycle_frames,total_frames)?;let timeline_ms=t.elapsed().as_secs_f64()*1000.0;
    let _=app.emit("engine-timing",json!({"id":job.project.id,"key":"fast-video-timeline-ms","milliseconds":timeline_ms}));

    let finalize_mark=Instant::now();verify(app,&out,final_duration,job).await?;write_side_files(job,&out,&durations,track_count)?;let bytes=fs::metadata(&out).ok().map(|m|m.len());let bitrate=video_bitrate(app,&out).await;let finalize_ms=finalize_mark.elapsed().as_secs_f64()*1000.0;let total_ms=wall.elapsed().as_secs_f64()*1000.0;
    let _=app.emit("engine-timing",json!({"id":job.project.id,"key":"fast-finalize-ms","milliseconds":finalize_ms}));
    let _=app.emit("engine-fast-path",json!({"id":job.project.id,"selected":true,"mode":plan.mode,"masterDuration":plan.master_seconds,"cycleFrames":plan.cycle_frames,"duration":final_duration,"audioMs":audio_ms,"masterMs":master_ms,"muxMs":mux_ms,"timelineMs":timeline_ms,"finalizeMs":finalize_ms,"totalMs":total_ms}));
    let _=app.emit("render-done",Progress{id:job.project.id.clone(),status:"done".into(),progress:100.0,stage:"Готово".into(),started_at:Some(started_ms),elapsed_sec:wall.elapsed().as_secs_f64(),eta_sec:Some(0.0),result_path:Some(out.to_string_lossy().into_owned()),result_bytes:bytes,actual_video_bitrate:bitrate,cpu_pct:None,ram_bytes:None,ram_total_bytes:None,ram_available_bytes:None,gpu_pct:None,encoder:Some(format!("hevc_videotoolbox + MP3 packet-copy ({})",plan.mode)),attempt:Some(1)});
    Ok(())
  }.await;
  match result{Ok(())=>{let _=fs::remove_dir_all(&work);Ok(())},Err(e)=>{let _=fs::remove_dir_all(&work);let _=fs::remove_file(&out);Err(e)}}
}

pub async fn try_render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<Option<()>,String>{
  let plan=match visual_plan(app,job).await{
    Ok(p)=>p,
    Err(reason)=>{let _=app.emit("engine-fast-fallback",json!({"id":job.project.id,"selected":false,"reason":reason,"phase":"eligibility"}));return Ok(None)}
  };
  let _=app.emit("engine-fast-path",json!({"id":job.project.id,"selected":true,"mode":plan.mode,"masterDuration":plan.master_seconds,"cycleFrames":plan.cycle_frames}));
  match run_fast(app,job,&plan,cancel.as_ref()).await{
    Ok(())=>Ok(Some(())),
    Err(e) if e==CANCELLED=>Err(e),
    Err(e)=>{let _=app.emit("engine-fast-fallback",json!({"id":job.project.id,"selected":false,"reason":e,"phase":"execution"}));Ok(None)}
  }
}
