use crate::{model::{Progress,QueueJob,RenderSettings},render};
use serde_json::json;
use std::{path::{Path,PathBuf},sync::{Arc,atomic::{AtomicBool,Ordering}},time::{Duration,Instant}};
use tauri::{AppHandle,Emitter};
use tauri_plugin_shell::{process::CommandEvent,ShellExt};

const CANCELLED:&str="__ENDLUME_CANCELLED__";
const IMAGE_EXT:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];
const STATIC_FPS:u32=2;
const STATIC_MASTER_SEC:f64=10.0;
const TARGET_TOTAL_KBPS_2H:f64=1110.0;

#[derive(Clone,Debug,PartialEq,Eq)]
struct AudioProfile{codec:String,sample_rate:String,channels:String}
#[derive(Clone,Debug)]
struct AudioInfo{duration:f64,profile:AudioProfile,bitrate_kbps:f64}

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

async fn probe_audio_info(app:&AppHandle,path:&str)->Result<AudioInfo,String>{
  let args=vec!["-v","error","-select_streams","a:0","-show_entries","stream=codec_name,sample_rate,channels,bit_rate:format=duration,bit_rate,size","-of","json",path].into_iter().map(String::from).collect();
  let (stdout,_)=output(app,"ffprobe",args).await?;
  let value:serde_json::Value=serde_json::from_slice(&stdout).map_err(|e|e.to_string())?;
  let stream=value.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()).ok_or_else(||format!("Не удалось определить аудиопрофиль: {path}"))?;
  let format=value.get("format").cloned().unwrap_or_default();
  let codec=stream.get("codec_name").and_then(|x|x.as_str()).unwrap_or("").to_ascii_lowercase();
  let sample_rate=stream.get("sample_rate").and_then(|x|x.as_str()).unwrap_or("").to_string();
  let channels=stream.get("channels").and_then(|x|x.as_u64()).map(|x|x.to_string()).unwrap_or_default();
  let duration=format.get("duration").and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok()).unwrap_or(180.0).max(0.2);
  let stream_bitrate=stream.get("bit_rate").and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok());
  let format_bitrate=format.get("bit_rate").and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok());
  let size_bits=format.get("size").and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok()).map(|x|x*8.0/duration);
  let bitrate_kbps=stream_bitrate.or(format_bitrate).or(size_bits).unwrap_or(256_000.0).max(32_000.0)/1000.0;
  if codec.is_empty()||sample_rate.is_empty()||channels.is_empty(){return Err(format!("Не удалось определить аудиопрофиль: {path}"))}
  Ok(AudioInfo{duration,profile:AudioProfile{codec,sample_rate,channels},bitrate_kbps})
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
    let event=tokio::time::timeout(Duration::from_millis(100),rx.recv()).await;
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

fn base_filter(s:&RenderSettings)->String{format!("scale={}:{}:force_original_aspect_ratio=decrease:flags=lanczos,pad={}:{}:(ow-iw)/2:(oh-ih)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,STATIC_FPS)}

fn playlist_average_kbps(infos:&[AudioInfo])->f64{
  let seconds=infos.iter().map(|x|x.duration).sum::<f64>().max(0.1);
  infos.iter().map(|x|x.bitrate_kbps*x.duration).sum::<f64>()/seconds
}

fn target_video_kbps(audio_kbps:f64)->u64{
  // Target about 1 GB per two hours for the typical music project. Audio remains byte-for-byte original;
  // only the repeating static video budget is adjusted. The first I-frame is forced to very high quality.
  (TARGET_TOTAL_KBPS_2H-audio_kbps-35.0).clamp(420.0,920.0).round() as u64
}

async fn build_hq_static_master(app:&AppHandle,job:&QueueJob,work:&Path,started:i64,timer:&Instant,cancel:&AtomicBool,video_kbps:u64)->Result<PathBuf,String>{
  let s=&job.settings;let g=(STATIC_FPS as f64*STATIC_MASTER_SEC).round().max(1.0) as u32;let g=g.to_string();let out=work.join("ultra-static-master.mp4");
  let avg=format!("{}k",video_kbps);let buf=format!("{}k",video_kbps.saturating_mul(2));
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",&STATIC_FPS.to_string(),"-i",job.project.media[0].as_str(),"-vf",&base_filter(s),"-t",&STATIC_MASTER_SEC.to_string(),"-an"].into_iter().map(String::from).collect();
  if s.codec.eq_ignore_ascii_case("h265"){
    let x265=format!("keyint={g}:min-keyint={g}:scenecut=0:vbv-maxrate={video_kbps}:vbv-bufsize={}:qpmin=8",video_kbps.saturating_mul(2));
    args.extend(vec!["-c:v","libx265","-preset","ultrafast","-b:v",&avg,"-maxrate",&avg,"-bufsize",&buf,"-g",&g,"-pix_fmt","yuv420p","-x265-params",&x265].into_iter().map(String::from));
  }else{
    let x264=format!("nal-hrd=cbr:filler=1:force-cfr=1:scenecut=0:keyint={g}:min-keyint={g}:vbv-init=1:zones=0,0,q=10");
    args.extend(vec!["-c:v","libx264","-preset","ultrafast","-tune","stillimage","-b:v",&avg,"-minrate",&avg,"-maxrate",&avg,"-bufsize",&buf,"-g",&g,"-keyint_min",&g,"-sc_threshold","0","-pix_fmt","yuv420p","-x264-params",&x264].into_iter().map(String::from));
  }
  args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"Собираю Ultra Static master",10.0,18.0,STATIC_MASTER_SEC,"ULTRA STATIC + ORIGINAL AUDIO",cancel).await?;Ok(out)
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
  let args=vec!["-v","error","-show_entries","format=duration:stream=index,codec_type,width,height","-of","json",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  let (raw,_)=output(app,"ffprobe",args).await?;let value:serde_json::Value=serde_json::from_slice(&raw).map_err(|e|e.to_string())?;
  let d=value.get("format").and_then(|x|x.get("duration")).and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok()).unwrap_or(0.0);
  if (d-expected).abs()>4.0{return Err(format!("Финальный файл имеет неверную длительность: {:.1} сек вместо {:.1}",d,expected))}
  let streams=value.get("streams").and_then(|x|x.as_array()).cloned().unwrap_or_default();
  if !streams.iter().any(|x|x.get("codec_type").and_then(|v|v.as_str())==Some("audio")){return Err("В финальном файле отсутствует аудиодорожка".into())}
  let video=streams.iter().find(|x|x.get("codec_type").and_then(|v|v.as_str())==Some("video")).ok_or("В финальном файле отсутствует видеодорожка")?;
  let w=video.get("width").and_then(|x|x.as_u64()).unwrap_or(0);let h=video.get("height").and_then(|x|x.as_u64()).unwrap_or(0);
  if w!=s.width as u64||h!=s.height as u64{return Err(format!("Неверное разрешение результата: {}x{}",w,h))}Ok(())
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
  emit_progress(app,job,started,&timer,1.0,"Анализ файлов — Fast Path",&encoder);
  let mut infos=Vec::with_capacity(job.project.audio.len());
  for a in &job.project.audio{infos.push(probe_audio_info(app,a).await?);}
  let first=infos.first().map(|x|x.profile.clone()).ok_or("Нет песен")?;
  if !mp4_copy_codec(&first.codec)||infos.iter().any(|x|x.profile!=first){return Ok(None)}
  let durations=infos.iter().map(|x|x.duration).collect::<Vec<_>>();let audio_kbps=playlist_average_kbps(&infos);let video_kbps=target_video_kbps(audio_kbps);
  emit_progress(app,job,started,&timer,7.0,"ORIGINAL AUDIO · без перекодирования",&encoder);
  let out_dir=PathBuf::from(&job.settings.output_dir);std::fs::create_dir_all(&out_dir).map_err(|e|e.to_string())?;let out=unique_output(&out_dir,&job.project.name);let work=std::env::temp_dir().join(format!("endlume-ultra-{}",job.project.id));let _=std::fs::remove_dir_all(&work);std::fs::create_dir_all(&work).map_err(|e|e.to_string())?;
  let result:Result<(),String>=async{
    let master=build_hq_static_master(app,job,&work,started,&timer,&cancel,video_kbps).await?;
    let target=job.settings.duration_hours*3600.0;let final_duration=smart_final_duration(target,&durations,&job.settings.duration_mode);let list=build_audio_list(&work,&job.project.audio,&durations,final_duration)?;
    let profile=format!("ULTRA STATIC {} FPS + ORIGINAL AUDIO",STATIC_FPS);emit_progress(app,job,started,&timer,30.0,"Мгновенный mux · video copy + original audio copy",&profile);
    let args=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-i",master.to_string_lossy().as_ref(),"-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-max_interleave_delta","0","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
    run_ffmpeg(app,job,started,&timer,args,"Собираю итоговое видео · STREAM COPY",31.0,64.0,final_duration,&profile,&cancel).await?;
    emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&profile);verify_result(app,&out,final_duration,&job.settings).await?;let stem=out.file_stem().and_then(|x|x.to_str()).unwrap_or(&job.project.name);write_side_files(job,&out_dir,&durations,final_duration,stem)?;
    let bytes=std::fs::metadata(&out).ok().map(|m|m.len());let bitrate=probe_video_bitrate(app,&out).await;let _=app.emit("engine-profile",json!({"id":job.project.id,"smartSize":true,"ultraStatic":true,"staticFps":STATIC_FPS,"originalAudio":true,"audioCodec":first.codec,"audioSampleRate":first.sample_rate,"audioKbps":audio_kbps,"targetVideoKbps":video_kbps,"targetSize":"~1 GB / 2h"}));
    let _=app.emit("render-done",Progress{id:job.project.id.clone(),status:"done".into(),progress:100.0,stage:"Готово · ULTRA STATIC · ORIGINAL AUDIO".into(),started_at:Some(started),elapsed_sec:timer.elapsed().as_secs_f64(),eta_sec:Some(0.0),result_path:Some(out.to_string_lossy().into_owned()),result_bytes:bytes,actual_video_bitrate:bitrate,cpu_pct:None,ram_bytes:None,ram_total_bytes:None,ram_available_bytes:None,gpu_pct:None,encoder:Some(profile),attempt:Some(1)});Ok(())
  }.await;
  let _=std::fs::remove_dir_all(&work);
  match result{Ok(())=>Ok(Some(())),Err(e)=>{let _=std::fs::remove_file(&out);Err(e)}}
}
