use crate::{model::{Progress,QueueJob,RenderSettings},render};
use serde_json::json;
use std::{path::{Path,PathBuf},sync::{Arc,atomic::{AtomicBool,Ordering}},time::{Duration,Instant}};
use tauri::{AppHandle,Emitter};
use tauri_plugin_shell::{process::CommandEvent,ShellExt};

const CANCELLED:&str="__ENDLUME_CANCELLED__";
const IMAGE_EXT:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];

#[derive(Clone,Debug,PartialEq,Eq)]
struct AudioProfile{codec:String,sample_rate:String,channels:String}

fn is_image(path:&str)->bool{Path::new(path).extension().and_then(|x|x.to_str()).map(|x|IMAGE_EXT.contains(&x.to_ascii_lowercase().as_str())).unwrap_or(false)}
fn safe_name(name:&str)->String{name.chars().map(|c|if ['/', '\\', ':', '*', '?', '"', '<', '>', '|'].contains(&c){'_'}else{c}).collect()}
fn unique_output(dir:&Path,name:&str)->PathBuf{let safe=safe_name(name);let mut p=dir.join(format!("{} — Ready Videos.mp4",safe));let mut n=2;while p.exists(){p=dir.join(format!("{} — Ready Videos_{}.mp4",safe,n));n+=1}p}
fn fmt_ts(sec:f64)->String{let s=sec.max(0.0).round() as u64;format!("{:02}:{:02}:{:02}",s/3600,(s%3600)/60,s%60)}
fn concat_line(path:&str)->String{format!("file '{}'",path.replace('\\',"/").replace("'","'\\''"))}

pub fn eligible(job:&QueueJob)->bool{
  job.project.media.len()==1&&is_image(&job.project.media[0])&&!job.project.audio.is_empty()
    &&job.effects.iter().all(|e|!e.enabled)
    &&job.subscribes.iter().all(|s|!s.effect.enabled)
    &&job.ambient.as_ref().map(|x|x.trim().is_empty()).unwrap_or(true)
    &&!job.settings.normalize_lufs
}

async fn output(app:&AppHandle,name:&str,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{
  let out=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
  Ok((out.stdout,out.stderr))
}

async fn probe_duration(app:&AppHandle,path:&str)->Result<f64,String>{
  let (stdout,_)=output(app,"ffprobe",vec!["-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",path].into_iter().map(String::from).collect()).await?;
  String::from_utf8_lossy(&stdout).trim().parse::<f64>().map_err(|_|format!("Не удалось определить длительность: {path}"))
}

async fn probe_audio_profile(app:&AppHandle,path:&str)->Result<AudioProfile,String>{
  let args=vec!["-v","error","-select_streams","a:0","-show_entries","stream=codec_name,sample_rate,channels","-of","json",path].into_iter().map(String::from).collect();
  let (stdout,_)=output(app,"ffprobe",args).await?;
  let value:serde_json::Value=serde_json::from_slice(&stdout).map_err(|e|e.to_string())?;
  let stream=value.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()).ok_or_else(||format!("Не удалось определить аудиопрофиль: {path}"))?;
  let codec=stream.get("codec_name").and_then(|x|x.as_str()).unwrap_or("").to_ascii_lowercase();
  let sample_rate=stream.get("sample_rate").and_then(|x|x.as_str()).unwrap_or("").to_string();
  let channels=stream.get("channels").and_then(|x|x.as_u64()).map(|x|x.to_string()).unwrap_or_default();
  if codec.is_empty()||sample_rate.is_empty()||channels.is_empty(){return Err(format!("Не удалось определить аудиопрофиль: {path}"))}
  Ok(AudioProfile{codec,sample_rate,channels})
}

fn mp4_copy_codec(codec:&str)->bool{matches!(codec,"aac"|"mp3"|"alac"|"ac3"|"eac3")}

fn emit_progress(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,progress:f64,stage:&str,encoder:&str){
  let elapsed=timer.elapsed().as_secs_f64();let eta=if progress>1.0{Some(elapsed*(100.0-progress)/progress)}else{None};
  let _=app.emit("render-progress",Progress{id:job.project.id.clone(),status:"rendering".into(),progress:progress.clamp(0.0,99.9),stage:stage.into(),started_at:Some(started),elapsed_sec:elapsed,eta_sec:eta,result_path:None,result_bytes:None,actual_video_bitrate:None,cpu_pct:None,ram_bytes:None,ram_total_bytes:None,ram_available_bytes:None,gpu_pct:None,encoder:Some(encoder.into()),attempt:Some(1)});
}

async fn run_ffmpeg(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,args:Vec<String>,stage:&str,base:f64,span:f64,expected_sec:f64,encoder:&str,cancel:&AtomicBool)->Result<(),String>{
  emit_progress(app,job,started,timer,base,stage,encoder);
  let (mut rx,child)=app.shell().sidecar("ffmpeg").map_err(|e|e.to_string())?.args(args).spawn().map_err(|e|e.to_string())?;
  let mut child=Some(child);let mut last=base;let mut stderr_tail=String::new();
  loop{
    if cancel.load(Ordering::SeqCst){if let Some(c)=child.take(){let _=c.kill();}return Err(CANCELLED.into())}
    let event=tokio::time::timeout(Duration::from_millis(120),rx.recv()).await;
    let ev=match event{Err(_)=>continue,Ok(Some(ev))=>ev,Ok(None)=>return Err("FFmpeg закрыл канал без статуса завершения".into())};
    match ev{
      CommandEvent::Stdout(bytes)|CommandEvent::Stderr(bytes)=>{
        let text=String::from_utf8_lossy(&bytes);stderr_tail.push_str(&text);if stderr_tail.len()>12000{stderr_tail=stderr_tail.split_off(stderr_tail.len()-9000)}
        for line in text.lines(){
          let raw=line.strip_prefix("out_time_us=").or_else(||line.strip_prefix("out_time_ms="));
          if let Some(raw)=raw.and_then(|x|x.parse::<f64>().ok()){
            let out_sec=raw/1_000_000.0;let frac=if expected_sec>0.0{(out_sec/expected_sec).clamp(0.0,1.0)}else{0.0};let p=base+frac*span;
            if p-last>=0.03{last=p;emit_progress(app,job,started,timer,p,stage,encoder)}
          }
        }
      },
      CommandEvent::Error(e)=>return Err(e),
      CommandEvent::Terminated(t)=>{
        child.take();
        if t.code.unwrap_or(1)!=0{return Err(if stderr_tail.trim().is_empty(){format!("FFmpeg завершился с кодом {:?}",t.code)}else{stderr_tail.lines().rev().take(14).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\n")})}
        break
      },
      _=>{}
    }
  }
  emit_progress(app,job,started,timer,base+span,stage,encoder);Ok(())
}

fn master_seconds(s:&RenderSettings)->f64{match s.width{0..=1920=>8.0,1921..=2560=>10.0,_=>12.0}}
fn base_filter(s:&RenderSettings)->String{format!("scale={}:{}:force_original_aspect_ratio=decrease:flags=lanczos,pad={}:{}:(ow-iw)/2:(oh-ih)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,s.fps)}

async fn build_hq_static_master(app:&AppHandle,job:&QueueJob,work:&Path,started:i64,timer:&Instant,cancel:&AtomicBool)->Result<(PathBuf,f64),String>{
  let s=&job.settings;let duration=master_seconds(s);let g=((s.fps.max(1) as f64*duration).round() as u32).max(1).to_string();let out=work.join("static-hq-master.mp4");
  let codec=if s.codec.eq_ignore_ascii_case("h265"){"libx265"}else{"libx264"};
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",&s.fps.to_string(),"-i",job.project.media[0].as_str(),"-vf",&base_filter(s),"-t",&duration.to_string(),"-an","-c:v",codec,"-preset","ultrafast"].into_iter().map(String::from).collect();
  if codec=="libx264"{args.extend(vec!["-tune","stillimage","-crf","12","-g",&g,"-keyint_min",&g,"-sc_threshold","0","-pix_fmt","yuv420p"].into_iter().map(String::from));}
  else{args.extend(vec!["-crf","14","-g",&g,"-pix_fmt","yuv420p"].into_iter().map(String::from));}
  args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"Собираю master-loop",12.0,20.0,duration,"HQ static + audio-copy",cancel).await?;Ok((out,duration))
}

fn smart_final_duration(target:f64,durations:&[f64],mode:&str)->f64{
  if mode!="whole-track"||durations.is_empty(){return target}
  let mut t=0.0;let mut i=0usize;while t<target{t+=durations[i%durations.len()].max(0.1);i+=1;}
  if t-target<=240.0{t}else{target}
}

fn build_audio_list(work:&Path,audio:&[String],durations:&[f64],final_duration:f64)->Result<PathBuf,String>{
  let mut lines=Vec::new();let mut t=0.0;let mut i=0usize;
  while t<final_duration+0.05{
    let idx=i%audio.len();lines.push(concat_line(&audio[idx]));t+=durations[idx].max(0.1);i+=1;if i>100000{return Err("Слишком много аудиосегментов".into())}
  }
  let list=work.join("original-audio-list.txt");std::fs::write(&list,lines.join("\n")).map_err(|e|e.to_string())?;Ok(list)
}

async fn verify_result(app:&AppHandle,out:&Path,expected:f64,s:&RenderSettings)->Result<(),String>{
  let d=probe_duration(app,out.to_string_lossy().as_ref()).await?;if (d-expected).abs()>4.0{return Err(format!("Финальный файл имеет неверную длительность: {:.1} сек вместо {:.1}",d,expected))}
  let (a,_)=output(app,"ffprobe",vec!["-v","error","-select_streams","a:0","-show_entries","stream=codec_type","-of","default=nw=1:nk=1",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await?;if !String::from_utf8_lossy(&a).contains("audio"){return Err("В финальном файле отсутствует аудиодорожка".into())}
  let (v,_)=output(app,"ffprobe",vec!["-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0:s=x",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await?;let got=String::from_utf8_lossy(&v);if !got.trim().starts_with(&format!("{}x{}",s.width,s.height)){return Err(format!("Неверное разрешение результата: {}",got.trim()))}Ok(())
}

async fn probe_video_bitrate(app:&AppHandle,path:&Path)->Option<u64>{
  let args=vec!["-v","error","-select_streams","v:0","-show_entries","stream=bit_rate","-of","default=nw=1:nk=1",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  output(app,"ffprobe",args).await.ok().and_then(|(o,_)|String::from_utf8_lossy(&o).trim().parse().ok())
}

fn write_side_files(job:&QueueJob,output_dir:&Path,durations:&[f64],final_duration:f64,result_stem:&str)->Result<(),String>{
  let name=safe_name(result_stem);let time_dir=output_dir.join("timecodes");let log_dir=output_dir.join("logs");std::fs::create_dir_all(&time_dir).map_err(|e|e.to_string())?;std::fs::create_dir_all(&log_dir).map_err(|e|e.to_string())?;
  let mut t=0.0;let mut i=0usize;let mut tc=String::new();while t<final_duration-0.1{let path=&job.project.audio[i%job.project.audio.len()];let title=Path::new(path).file_stem().and_then(|x|x.to_str()).unwrap_or("Track");tc.push_str(&format!("{} {}\n",fmt_ts(t),title));t+=durations[i%durations.len()].max(0.1);i+=1;if i>10000{break}}
  std::fs::write(time_dir.join(format!("{} — timecodes.txt",name)),tc).map_err(|e|e.to_string())?;let tracklist=job.project.audio.iter().enumerate().map(|(i,p)|format!("{}. {}",i+1,Path::new(p).file_name().and_then(|x|x.to_str()).unwrap_or(p))).collect::<Vec<_>>().join("\n");std::fs::write(output_dir.join(format!("{} — tracklist.txt",name)),tracklist).map_err(|e|e.to_string())?;std::fs::write(log_dir.join(format!("{} — project.json",name)),serde_json::to_vec_pretty(job).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;Ok(())
}

pub async fn try_render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<Option<()>,String>{
  if !eligible(job){return Ok(None)}
  for p in &job.project.audio{if !Path::new(p).is_file(){return Err(format!("Не найден аудиофайл: {p}"))}}
  if !Path::new(&job.project.media[0]).is_file(){return Err(format!("Не найден файл изображения: {}",job.project.media[0]))}
  let started=chrono::Utc::now().timestamp_millis();let timer=Instant::now();let encoder=render::choose_encoder(app,&job.settings).await;
  emit_progress(app,job,started,&timer,1.0,"Анализ файлов",&encoder);
  let mut durations=Vec::with_capacity(job.project.audio.len());let mut profiles=Vec::with_capacity(job.project.audio.len());
  for a in &job.project.audio{durations.push(probe_duration(app,a).await.unwrap_or(180.0).max(0.2));profiles.push(probe_audio_profile(app,a).await?);}
  let first=profiles.first().cloned().ok_or("Нет песен")?;
  if !mp4_copy_codec(&first.codec)||profiles.iter().any(|p|p!=&first){return Ok(None)}
  emit_progress(app,job,started,&timer,8.0,"Оригинальный звук совместим — без перекодирования",&encoder);
  let out_dir=PathBuf::from(&job.settings.output_dir);std::fs::create_dir_all(&out_dir).map_err(|e|e.to_string())?;let out=unique_output(&out_dir,&job.project.name);let work=std::env::temp_dir().join(format!("endlume-fast-{}",job.project.id));let _=std::fs::remove_dir_all(&work);std::fs::create_dir_all(&work).map_err(|e|e.to_string())?;
  let result:Result<(),String>=async{
    let (master,master_duration)=build_hq_static_master(app,job,&work,started,&timer,&cancel).await?;
    let target=job.settings.duration_hours*3600.0;let final_duration=smart_final_duration(target,&durations,&job.settings.duration_mode);let list=build_audio_list(&work,&job.project.audio,&durations,final_duration)?;
    emit_progress(app,job,started,&timer,34.0,"Подготавливаю музыку — ORIGINAL STREAM COPY",&encoder);
    let args=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-i",master.to_string_lossy().as_ref(),"-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
    run_ffmpeg(app,job,started,&timer,args,"Собираю итоговое видео — без повторного кодирования",35.0,61.0,final_duration,"HQ static + audio-copy",&cancel).await?;
    let _=master_duration;emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe","HQ static + audio-copy");verify_result(app,&out,final_duration,&job.settings).await?;let stem=out.file_stem().and_then(|x|x.to_str()).unwrap_or(&job.project.name);write_side_files(job,&out_dir,&durations,final_duration,stem)?;
    let bytes=std::fs::metadata(&out).ok().map(|m|m.len());let bitrate=probe_video_bitrate(app,&out).await;let _=app.emit("engine-profile",json!({"id":job.project.id,"smartSize":true,"originalAudio":true,"audioCodec":first.codec,"audioSampleRate":first.sample_rate}));
    let _=app.emit("render-done",Progress{id:job.project.id.clone(),status:"done".into(),progress:100.0,stage:"Готово · ORIGINAL AUDIO".into(),started_at:Some(started),elapsed_sec:timer.elapsed().as_secs_f64(),eta_sec:Some(0.0),result_path:Some(out.to_string_lossy().into_owned()),result_bytes:bytes,actual_video_bitrate:bitrate,cpu_pct:None,ram_bytes:None,ram_total_bytes:None,ram_available_bytes:None,gpu_pct:None,encoder:Some("HQ static + audio-copy".into()),attempt:Some(1)});Ok(())
  }.await;
  let _=std::fs::remove_dir_all(&work);
  match result{Ok(())=>Ok(Some(())),Err(e)=>{let _=std::fs::remove_file(&out);Err(e)}}
}
