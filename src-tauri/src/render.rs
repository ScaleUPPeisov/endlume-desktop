use crate::{cache,model::{EffectPreset,Progress,QueueJob,RenderSettings,SubscribePreset}};
use serde_json::json;
use std::{collections::HashMap,path::{Path,PathBuf},sync::{Arc,OnceLock,atomic::{AtomicBool,Ordering}},time::{Duration,Instant}};
use sysinfo::{Pid,ProcessesToUpdate,System};
use tauri::{AppHandle,Emitter};
use tauri_plugin_shell::{process::CommandEvent,ShellExt};

const IMAGE_EXT:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];
const CANCELLED:&str="__ENDLUME_CANCELLED__";
static ENCODER_CACHE:OnceLock<parking_lot::Mutex<HashMap<String,String>>>=OnceLock::new();
static AUDIO_ENCODER_CACHE:OnceLock<String>=OnceLock::new();

#[derive(Clone)]
struct SubEvent{start:f64,end:f64,sub:SubscribePreset,event_start:f64}

enum VisualSource{Loop(PathBuf),Long(PathBuf)}
enum AudioSource{Loop(PathBuf),Long(PathBuf)}

fn is_image(path:&str)->bool{Path::new(path).extension().and_then(|x|x.to_str()).map(|x|IMAGE_EXT.contains(&x.to_ascii_lowercase().as_str())).unwrap_or(false)}
fn safe_name(name:&str)->String{name.chars().map(|c|if ['/', '\\', ':', '*', '?', '"', '<', '>', '|'].contains(&c){'_'}else{c}).collect()}
fn unique_output(dir:&Path,name:&str)->PathBuf{let safe=safe_name(name);let mut p=dir.join(format!("{} — Ready Videos.mp4",safe));let mut n=2;while p.exists(){p=dir.join(format!("{} — Ready Videos_{}.mp4",safe,n));n+=1}p}
fn fmt_ts(sec:f64)->String{let s=sec.max(0.0).round() as u64;format!("{:02}:{:02}:{:02}",s/3600,(s%3600)/60,s%60)}
fn color_ffmpeg(hex:&str)->String{format!("0x{}",hex.trim().trim_start_matches('#').trim_start_matches("0x"))}
fn emit_timing(app:&AppHandle,id:&str,key:&str,sec:f64){let _=app.emit("engine-timing",json!({"id":id,"key":key,"seconds":sec}));}

async fn output(app:&AppHandle,name:&str,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{
  let out=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
  Ok((out.stdout,out.stderr))
}

async fn probe_duration(app:&AppHandle,path:&str)->Result<f64,String>{
  let (stdout,_)=output(app,"ffprobe",vec!["-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",path].into_iter().map(String::from).collect()).await?;
  String::from_utf8_lossy(&stdout).trim().parse::<f64>().map_err(|_|format!("Не удалось определить длительность: {path}"))
}
async fn probe_video_bitrate(app:&AppHandle,path:&Path)->Option<u64>{
  let args=vec!["-v","error","-select_streams","v:0","-show_entries","stream=bit_rate","-of","default=nw=1:nk=1",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  output(app,"ffprobe",args).await.ok().and_then(|(o,_)|String::from_utf8_lossy(&o).trim().parse().ok())
}
async fn probe_has_audio(app:&AppHandle,path:&Path)->bool{
  let args=vec!["-v","error","-select_streams","a:0","-show_entries","stream=codec_type","-of","default=nw=1:nk=1",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  output(app,"ffprobe",args).await.ok().map(|(o,_)|String::from_utf8_lossy(&o).contains("audio")).unwrap_or(false)
}
async fn encoder_works(app:&AppHandle,encoder:&str)->bool{
  let args=vec!["-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=black:s=640x360:r=30","-t","0.35","-an","-c:v",encoder,"-f","null","-"].into_iter().map(String::from).collect();
  output(app,"ffmpeg",args).await.is_ok()
}

pub async fn choose_encoder(app:&AppHandle,s:&RenderSettings)->String{
  let h265=s.codec.eq_ignore_ascii_case("h265");
  let cache_key=if h265{"h265"}else{"h264"};
  let cache=ENCODER_CACHE.get_or_init(||parking_lot::Mutex::new(HashMap::new()));
  if let Some(found)=cache.lock().get(cache_key).cloned(){return found}

  #[cfg(target_os="macos")]
  let candidates=if h265{vec!["hevc_videotoolbox","libx265"]}else{vec!["h264_videotoolbox","libx264"]};
  #[cfg(target_os="windows")]
  let candidates=if h265{vec!["hevc_nvenc","hevc_qsv","hevc_amf","libx265"]}else{vec!["h264_nvenc","h264_qsv","h264_amf","libx264"]};
  #[cfg(not(any(target_os="macos",target_os="windows")))]
  let candidates=if h265{vec!["libx265"]}else{vec!["libx264"]};
  for c in candidates{if encoder_works(app,c).await{let selected=c.to_string();cache.lock().insert(cache_key.into(),selected.clone());return selected}}
  let selected=if h265{"libx265".to_string()}else{"libx264".to_string()};cache.lock().insert(cache_key.into(),selected.clone());selected
}

fn static_video_kbps(s:&RenderSettings)->u64{
  // Smart Size budget. At 4K: ~0.62 Mbit/s base video + one high-quality
  // keyframe per 12 s + AAC 320k => around 0.9–1.1 GB for two hours.
  match s.width{
    0..=1920=>450,
    1921..=2560=>520,
    _=>620,
  }
}

fn static_master_seconds(s:&RenderSettings)->f64{match s.width{0..=1920=>8.0,1921..=2560=>10.0,_=>12.0}}

fn static_smart_encoder_args(s:&RenderSettings)->Vec<String>{
  let duration=static_master_seconds(s);
  let gop=(s.fps.max(1) as f64*duration).round().max(1.0) as u32;
  let g=gop.to_string();
  if s.codec.eq_ignore_ascii_case("h265"){
    // H.265 fallback keeps the same short-master concept. H.264 is the
    // primary tested Smart Size path for the current macOS release.
    let avg=format!("{}k",(static_video_kbps(s) as f64*0.82).round() as u64);
    vec!["-c:v","libx265","-preset","ultrafast","-tune","ssim","-b:v",&avg,"-maxrate","12M","-bufsize","80M","-g",&g,"-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }else{
    let avg=format!("{}k",static_video_kbps(s));
    // First I-frame is forced to a high-quality quantizer. This prevents the
    // 0–5 s degradation seen with plain low-ABR encoding. The remaining
    // identical frames are cheap, so the repeated master stays around 1 GB.
    vec!["-c:v","libx264","-preset","ultrafast","-tune","stillimage","-b:v",&avg,"-maxrate","20M","-bufsize","100M","-g",&g,"-keyint_min",&g,"-sc_threshold","0","-pix_fmt","yuv420p","-x264-params","vbv-init=1:zones=0,0,q=14"].into_iter().map(String::from).collect()
  }
}

async fn encode_static_smart_clip(app:&AppHandle,job:&QueueJob,media:&str,out:&Path,started:i64,timer:&Instant,encoder:&str,attempt:u32,cancel:&AtomicBool,base:f64,span:f64)->Result<f64,String>{
  let s=&job.settings;let duration=static_master_seconds(s);
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",&s.fps.to_string(),"-i",media,"-filter_complex",&format!("{}[outv]",base_filter(s,"0:v")),"-map","[outv]","-t",&duration.to_string(),"-an"].into_iter().map(String::from).collect();
  args.extend(static_smart_encoder_args(s));
  args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"Собираю Smart Size master",base,span,duration,encoder,attempt,cancel).await?;
  Ok(duration)
}

fn encoder_args(encoder:&str,s:&RenderSettings,static_content:bool)->Vec<String>{
  // Pure image projects get a dedicated low-bitrate long-GOP profile.
  // Bitrate profile is retained for encoded video/effect variants; pure still images use the dedicated Smart Size master above.
  let user_mbps=s.bitrate_mbps.clamp(1.0,100.0);
  let video_kbps=if static_content{static_video_kbps(s) as f64}else{user_mbps*1000.0};
  let cap=if static_content{format!("{}k",((video_kbps*8.0).max(6000.0)).round() as u64)}else{format!("{}M",user_mbps)};
  let buf=if static_content{format!("{}k",((video_kbps*16.0).max(12000.0)).round() as u64)}else{format!("{}M",(user_mbps*2.0).clamp(2.0,200.0))};
  let avg=if static_content{format!("{}k",video_kbps.round() as u64)}else{format!("{}M",user_mbps)};
  let gop=(s.fps.max(1)*if static_content{static_master_seconds(s).round() as u32}else{2}).to_string();
  let raw:Vec<&str>=match encoder{
    "libx264"=>if static_content{vec!["-c:v","libx264","-preset","veryfast","-b:v",&avg,"-maxrate",&cap,"-bufsize",&buf,"-g",&gop,"-keyint_min",&gop,"-sc_threshold","0","-pix_fmt","yuv420p"]}else{vec!["-c:v","libx264","-preset",s.preset.as_str(),"-crf","17","-maxrate",&cap,"-bufsize",&buf,"-pix_fmt","yuv420p"]},
    "libx265"=>if static_content{vec!["-c:v","libx265","-preset","veryfast","-b:v",&avg,"-maxrate",&cap,"-bufsize",&buf,"-g",&gop,"-pix_fmt","yuv420p"]}else{vec!["-c:v","libx265","-preset",s.preset.as_str(),"-crf","19","-maxrate",&cap,"-bufsize",&buf,"-pix_fmt","yuv420p"]},
    "h264_nvenc"=>if static_content{vec!["-c:v","h264_nvenc","-preset","p4","-rc","vbr","-b:v",&avg,"-maxrate",&cap,"-bufsize",&buf,"-g",&gop,"-pix_fmt","yuv420p"]}else{vec!["-c:v","h264_nvenc","-preset","p4","-rc","vbr","-cq","18","-b:v","0","-maxrate",&cap,"-bufsize",&buf,"-pix_fmt","yuv420p"]},
    "hevc_nvenc"=>if static_content{vec!["-c:v","hevc_nvenc","-preset","p4","-rc","vbr","-b:v",&avg,"-maxrate",&cap,"-bufsize",&buf,"-g",&gop,"-pix_fmt","yuv420p"]}else{vec!["-c:v","hevc_nvenc","-preset","p4","-rc","vbr","-cq","20","-b:v","0","-maxrate",&cap,"-bufsize",&buf,"-pix_fmt","yuv420p"]},
    "h264_qsv"=>if static_content{vec!["-c:v","h264_qsv","-b:v",&avg,"-maxrate",&cap,"-bufsize",&buf,"-g",&gop,"-pix_fmt","nv12"]}else{vec!["-c:v","h264_qsv","-global_quality","18","-maxrate",&cap,"-bufsize",&buf,"-pix_fmt","nv12"]},
    "hevc_qsv"=>if static_content{vec!["-c:v","hevc_qsv","-b:v",&avg,"-maxrate",&cap,"-bufsize",&buf,"-g",&gop,"-pix_fmt","nv12"]}else{vec!["-c:v","hevc_qsv","-global_quality","20","-maxrate",&cap,"-bufsize",&buf,"-pix_fmt","nv12"]},
    "h264_amf"=>if static_content{vec!["-c:v","h264_amf","-quality","speed","-rc","vbr_peak","-b:v",&avg,"-maxrate",&cap,"-g",&gop,"-pix_fmt","yuv420p"]}else{vec!["-c:v","h264_amf","-quality","balanced","-rc","vbr_peak","-qp_i","18","-maxrate",&cap,"-pix_fmt","yuv420p"]},
    "hevc_amf"=>if static_content{vec!["-c:v","hevc_amf","-quality","speed","-rc","vbr_peak","-b:v",&avg,"-maxrate",&cap,"-g",&gop,"-pix_fmt","yuv420p"]}else{vec!["-c:v","hevc_amf","-quality","balanced","-rc","vbr_peak","-qp_i","20","-maxrate",&cap,"-pix_fmt","yuv420p"]},
    "h264_videotoolbox"=>if static_content{vec!["-c:v","h264_videotoolbox","-realtime","0","-prio_speed","0","-power_efficient","0","-b:v",&avg,"-maxrate",&cap,"-bufsize",&buf,"-g",&gop,"-pix_fmt","yuv420p"]}else{vec!["-c:v","h264_videotoolbox","-q:v","70","-maxrate",&cap,"-bufsize",&buf,"-pix_fmt","yuv420p"]},
    "hevc_videotoolbox"=>if static_content{vec!["-c:v","hevc_videotoolbox","-realtime","0","-prio_speed","0","-power_efficient","0","-b:v",&avg,"-maxrate",&cap,"-bufsize",&buf,"-g",&gop,"-pix_fmt","yuv420p"]}else{vec!["-c:v","hevc_videotoolbox","-q:v","65","-maxrate",&cap,"-bufsize",&buf,"-pix_fmt","yuv420p"]},
    _=>if static_content{vec!["-c:v","libx264","-preset","veryfast","-b:v",&avg,"-maxrate",&cap,"-bufsize",&buf,"-g",&gop,"-keyint_min",&gop,"-sc_threshold","0","-pix_fmt","yuv420p"]}else{vec!["-c:v","libx264","-preset","fast","-crf","17","-maxrate",&cap,"-bufsize",&buf,"-pix_fmt","yuv420p"]}
  };
  raw.into_iter().map(String::from).collect()
}

async fn audio_encoder_works(app:&AppHandle,encoder:&str)->bool{
  let args=vec!["-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=440:sample_rate=48000","-t","0.2","-c:a",encoder,"-b:a","192k","-f","adts","-"] .into_iter().map(String::from).collect();
  output(app,"ffmpeg",args).await.is_ok()
}

async fn choose_audio_encoder(app:&AppHandle)->String{
  if let Some(v)=AUDIO_ENCODER_CACHE.get(){return v.clone()}
  #[cfg(target_os="macos")]
  let candidates=vec!["aac_at","aac"];
  #[cfg(not(target_os="macos"))]
  let candidates=vec!["aac"];
  let mut selected="aac".to_string();
  for c in candidates{if audio_encoder_works(app,c).await{selected=c.to_string();break}}
  let _=AUDIO_ENCODER_CACHE.set(selected.clone());selected
}

fn audio_encoder_args(encoder:&str)->Vec<String>{
  if encoder=="aac_at"{
    vec!["-c:a","aac_at","-b:a","320k","-aac_at_mode","cvbr","-aac_at_quality","2","-ar","48000","-ac","2"].into_iter().map(String::from).collect()
  }else{
    vec!["-c:a","aac","-b:a","320k","-ar","48000","-ac","2"].into_iter().map(String::from).collect()
  }
}

fn emit_progress(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,progress:f64,stage:&str,encoder:&str,attempt:u32,metrics:Option<(f32,u64,u64,u64)>){
  let elapsed=timer.elapsed().as_secs_f64();let eta=if progress>1.0{Some(elapsed*(100.0-progress)/progress)}else{None};
  let (cpu,ram,total,available)=metrics.unwrap_or((0.0,0,0,0));
  let _=app.emit("render-progress",Progress{id:job.project.id.clone(),status:"rendering".into(),progress:progress.clamp(0.0,99.9),stage:stage.into(),started_at:Some(started),elapsed_sec:elapsed,eta_sec:eta,result_path:None,result_bytes:None,actual_video_bitrate:None,cpu_pct:metrics.map(|_|cpu),ram_bytes:metrics.map(|_|ram),ram_total_bytes:metrics.map(|_|total),ram_available_bytes:metrics.map(|_|available),gpu_pct:None,encoder:Some(encoder.into()),attempt:Some(attempt)});
}

async fn run_ffmpeg(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,args:Vec<String>,stage:&str,base:f64,span:f64,expected_sec:f64,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(),String>{
  emit_progress(app,job,started,timer,base,stage,encoder,attempt,None);
  let (mut rx,child)=app.shell().sidecar("ffmpeg").map_err(|e|e.to_string())?.args(args).spawn().map_err(|e|e.to_string())?;
  let pid=child.pid();let mut child=Some(child);let mut last=base;let mut stderr_tail=String::new();let mut sys=System::new_all();let mut metric_tick=Instant::now();
  loop{
    if cancel.load(Ordering::SeqCst){if let Some(c)=child.take(){let _=c.kill();}return Err(CANCELLED.into())}
    let event=tokio::time::timeout(Duration::from_millis(160),rx.recv()).await;
    if metric_tick.elapsed()>=Duration::from_millis(480){
      let pids=[Pid::from_u32(pid)];sys.refresh_processes(ProcessesToUpdate::Some(&pids),true);sys.refresh_memory();
      if let Some(p)=sys.process(pids[0]){let cpu=(p.cpu_usage()/(sys.cpus().len().max(1) as f32)).clamp(0.0,100.0);emit_progress(app,job,started,timer,last,stage,encoder,attempt,Some((cpu,p.memory(),sys.total_memory(),sys.available_memory())))}
      metric_tick=Instant::now();
    }
    let ev=match event{Err(_)=>continue,Ok(Some(ev))=>ev,Ok(None)=>return Err("FFmpeg закрыл канал без статуса завершения".into())};
    match ev{
      CommandEvent::Stdout(bytes)|CommandEvent::Stderr(bytes)=>{
        let text=String::from_utf8_lossy(&bytes);stderr_tail.push_str(&text);if stderr_tail.len()>12000{stderr_tail=stderr_tail.split_off(stderr_tail.len()-9000)}
        for line in text.lines(){
          let raw=line.strip_prefix("out_time_us=").or_else(||line.strip_prefix("out_time_ms="));
          if let Some(raw)=raw.and_then(|x|x.parse::<f64>().ok()){
            let out_sec=raw/1_000_000.0;let frac=if expected_sec>0.0{(out_sec/expected_sec).clamp(0.0,1.0)}else{0.0};let p=base+frac*span;
            if p-last>=0.01{last=p;emit_progress(app,job,started,timer,p,stage,encoder,attempt,None)}
          }
        }
      },
      CommandEvent::Error(e)=>return Err(e),
      CommandEvent::Terminated(t)=>{
        child.take();
        if t.code.unwrap_or(1)!=0{return Err(if stderr_tail.trim().is_empty(){format!("FFmpeg завершился с кодом {:?}",t.code)}else{stderr_tail.lines().rev().take(12).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\n")})}
        break
      },
      _=>{}
    }
  }
  emit_progress(app,job,started,timer,base+span,stage,encoder,attempt,None);Ok(())
}

fn base_filter(s:&RenderSettings,label:&str)->String{format!("[{label}]scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,s.fps)}

async fn build_media_clip(app:&AppHandle,job:&QueueJob,media:&str,index:usize,total:usize,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,f64),String>{
  let s=&job.settings;let clip=work.join(format!("source-{index:03}.mp4"));let base=8.0+(index as f64/total.max(1) as f64)*14.0;let span=14.0/total.max(1) as f64;
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();let duration:f64;let graph:String;
  if is_image(media) && total==1 && job.effects.iter().all(|e|!e.enabled) && job.subscribes.iter().all(|e|!e.effect.enabled){
    duration=encode_static_smart_clip(app,job,media,&clip,started,timer,encoder,attempt,cancel,base,span).await?;
    return Ok((clip,duration));
  }else if is_image(media){
    duration=10.0;args.extend(vec!["-loop","1","-framerate",&s.fps.to_string(),"-i",media].into_iter().map(String::from));graph=format!("{}[outv]",base_filter(s,"0:v"));
  }else{
    let d=probe_duration(app,media).await.unwrap_or(5.0).clamp(1.0,60.0);
    match s.loop_mode.as_str(){
      "crossfade"=>{let cf=s.crossfade_sec.min((d/3.0).max(0.15)).max(0.1);duration=d;args.extend(vec!["-i",media,"-i",media].into_iter().map(String::from));graph=format!("[0:v]trim=duration={d},setpts=PTS-STARTPTS[a];[1:v]trim=duration={d},setpts=PTS-STARTPTS[b];[a][b]xfade=transition=fade:duration={cf}:offset={},trim=start={cf}:duration={d},setpts=PTS-STARTPTS[x];{}[outv]",(d-cf).max(0.1),base_filter(s,"x"));},
      "pingpong"=>{duration=d*2.0;args.extend(vec!["-i",media].into_iter().map(String::from));graph=format!("[0:v]trim=duration={d},setpts=PTS-STARTPTS,split[f][r];[r]reverse[rr];[f][rr]concat=n=2:v=1:a=0[x];{}[outv]",base_filter(s,"x"));},
      _=>{duration=d;args.extend(vec!["-i",media].into_iter().map(String::from));graph=format!("{}[outv]",base_filter(s,"0:v"));}
    }
  }
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t",&duration.to_string(),"-an"].into_iter().map(String::from));if is_image(media){args.extend(static_smart_encoder_args(s));}else{args.extend(encoder_args(encoder,s,false));}args.extend(vec!["-progress","pipe:1","-y",clip.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,&format!("Подготавливаю медиа {}/{}",index+1,total),base,span,duration,encoder,attempt,cancel).await?;Ok((clip,duration))
}

async fn build_source_master(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,f64),String>{
  if job.project.media.is_empty(){return Err("Нет изображения или видео".into())}
  let mark=Instant::now();let total=job.project.media.len();let mut clips=Vec::new();let mut total_duration=0.0;
  for (i,m) in job.project.media.iter().enumerate(){let (p,d)=build_media_clip(app,job,m,i,total,started,timer,work,encoder,attempt,cancel).await?;clips.push(p);total_duration+=d;}
  let master=work.join("source-master.mp4");
  if clips.len()==1{std::fs::copy(&clips[0],&master).map_err(|e|e.to_string())?;}else{
    let list=work.join("source-concat.txt");let text=clips.iter().map(|p|format!("file '{}'",p.to_string_lossy().replace('\\',"/"))).collect::<Vec<_>>().join("\n");std::fs::write(&list,text).map_err(|e|e.to_string())?;
    let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-an","-c:v","copy","-progress","pipe:1","-y",master.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
    run_ffmpeg(app,job,started,timer,args,"Собираю master-loop из медиа",22.0,4.0,total_duration,encoder,attempt,cancel).await?;
  }
  emit_timing(app,&job.project.id,"master-loop",mark.elapsed().as_secs_f64());Ok((master,total_duration.max(0.2)))
}

fn apply_effects_filter(mut graph:String,mut base:String,effects:&[EffectPreset],s:&RenderSettings,input_start:usize)->(String,String){
  for (n,e) in effects.iter().filter(|e|e.enabled&&!e.source.trim().is_empty()).enumerate(){
    let idx=input_start+n;let fx=format!("fx{n}");let next=format!("b{}",n+1);
    if e.mode=="screen"||e.mode=="screen-cache"{
      let prep=if e.mode=="screen-cache"{format!("[{idx}:v]fps={},scale={}:{},setsar=1",s.fps,s.width,s.height)}else{format!("[{idx}:v]fps={},scale={}:{},setsar=1,eq=saturation={}",s.fps,s.width,s.height,e.saturation)};
      graph.push_str(&format!(";{prep}[{fx}];[{base}][{fx}]blend=all_mode=screen:all_opacity=1[{next}]"));
    }else{
      let prep=if e.mode=="prealpha"{format!("[{idx}:v]fps={},format=argb",s.fps)}else if e.mode=="luma"{format!("[{idx}:v]fps={},format=rgba,eq=saturation={},lumakey=threshold={}:tolerance={}:softness=0.08",s.fps,e.saturation,e.luma_threshold,e.luma_tolerance)}else{format!("[{idx}:v]fps={},format=rgba,chromakey={}:{}:{}",s.fps,color_ffmpeg(&e.key_color),e.similarity.max(0.00001),e.blend)};
      let scale=if e.fullscreen{format!("scale={}:{}",s.width,s.height)}else{format!("scale=iw*{}:ih*{}",e.scale.max(0.01),e.scale.max(0.01))};let x=if e.fullscreen{"0".into()}else{format!("(W-w)*{}",e.x.clamp(0.0,1.0))};let y=if e.fullscreen{"0".into()}else{format!("(H-h)*{}",e.y.clamp(0.0,1.0))};
      graph.push_str(&format!(";{prep},{scale}[{fx}];[{base}][{fx}]overlay=x='{x}':y='{y}':shortest=1:eof_action=repeat[{next}]"));
    }
    base=next;
  }
  (graph,base)
}

async fn prepare_overlays(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,encoder:&str,attempt:u32)->Result<(Vec<EffectPreset>,Vec<SubscribePreset>),String>{
  emit_progress(app,job,started,timer,26.0,"Проверяю кэш Effects и Subscribe",encoder,attempt,None);let mark=Instant::now();let mut fx=Vec::new();let mut subs=Vec::new();
  for e in &job.effects{fx.push(cache::prepare(app,e,job.settings.fps).await?)}
  for s in &job.subscribes{let mut p=s.clone();p.effect=cache::prepare(app,&s.effect,job.settings.fps).await?;subs.push(p)}
  emit_timing(app,&job.project.id,"effects-cache",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,31.0,"Кэш Effects и Subscribe готов",encoder,attempt,None);Ok((fx,subs))
}

fn active_effects_at(effects:&[EffectPreset],t:f64,final_duration:f64)->Vec<EffectPreset>{
  effects.iter().filter(|e|e.enabled&&e.start_sec<=t&&e.end_sec.unwrap_or(final_duration)>t).cloned().collect()
}
fn state_key(effects:&[EffectPreset])->String{let mut ids=effects.iter().map(|e|e.id.clone()).collect::<Vec<_>>();ids.sort();ids.join("|")}

async fn build_variant(app:&AppHandle,job:&QueueJob,source_master:&Path,master_duration:f64,effects:&[EffectPreset],work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,variant_no:usize,started:i64,timer:&Instant)->Result<PathBuf,String>{
  if effects.is_empty(){return Ok(source_master.to_path_buf())}
  let out=work.join(format!("variant-{variant_no:03}.mp4"));let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-i",source_master.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  for e in effects{args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}
  let (graph,last)=apply_effects_filter("[0:v]setpts=PTS-STARTPTS[b0]".into(),"b0".into(),effects,&job.settings,1);let graph=format!("{graph};[{last}]format=yuv420p[outv]");
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t",&master_duration.to_string(),"-an"].into_iter().map(String::from));args.extend(encoder_args(encoder,&job.settings,false));args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"Подготавливаю вариант Effects",32.0,3.0,master_duration,encoder,attempt,cancel).await?;Ok(out)
}

async fn build_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
  let mark=Instant::now();let mut durations=Vec::new();for a in &job.project.audio{durations.push(probe_duration(app,a).await.unwrap_or(180.0).max(0.2));}
  if job.project.audio.is_empty(){return Err("Нет песен".into())}
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();for a in &job.project.audio{args.extend(vec!["-i",a.as_str()].into_iter().map(String::from));}
  let ambient_index=job.project.audio.len();if let Some(a)=job.ambient.as_ref().filter(|p|!p.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",a.as_str()].into_iter().map(String::from));}
  let mut labels=Vec::new();let mut graph=String::new();for i in 0..job.project.audio.len(){if i>0{graph.push(';')}graph.push_str(&format!("[{i}:a]aresample=48000,asetpts=N/SR/TB[a{i}]"));labels.push(format!("a{i}"));}
  let cf=job.settings.crossfade_sec.clamp(0.0,10.0);let mut last=labels[0].clone();for i in 1..labels.len(){let out=format!("x{i}");graph.push_str(&format!(";[{last}][{}]acrossfade=d={}:c1=tri:c2=tri[{out}]",labels[i],cf));last=out;}
  let music="music";if job.settings.normalize_lufs{graph.push_str(&format!(";[{last}]loudnorm=I=-14:TP=-1.5:LRA=11[{music}]"));}else{graph.push_str(&format!(";[{last}]anull[{music}]"));}
  if job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false){graph.push_str(&format!(";[{ambient_index}:a]aresample=48000,volume=0.18[amb];[{music}][amb]amix=inputs=2:duration=first:weights='1 1':normalize=0,alimiter=limit=0.97[outa]"));}else{graph.push_str(&format!(";[{music}]alimiter=limit=0.97[outa]"));}
  let audio_encoder=choose_audio_encoder(app).await;let cycle=work.join("audio-cycle.m4a");args.extend(vec!["-filter_complex",&graph,"-map","[outa]"].into_iter().map(String::from));args.extend(audio_encoder_args(&audio_encoder));args.extend(vec!["-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from));
  let expected=(durations.iter().sum::<f64>()-cf*((durations.len().saturating_sub(1)) as f64)).max(1.0);run_ffmpeg(app,job,started,timer,args,"Подготавливаю музыку",35.0,20.0,expected,encoder,attempt,cancel).await?;
  let cycle_duration=probe_duration(app,cycle.to_string_lossy().as_ref()).await.unwrap_or(expected);emit_timing(app,&job.project.id,"audio",mark.elapsed().as_secs_f64());Ok((cycle,durations,cycle_duration))
}

fn smart_final_duration(target:f64,durations:&[f64],crossfade:f64,mode:&str)->f64{if mode!="whole-track"||durations.is_empty(){return target}let mut t=0.0;let mut i=0usize;while t<target{let add=(durations[i%durations.len()]-if t>0.0{crossfade}else{0.0}).max(0.1);t+=add;i+=1;}if t-target<=240.0{t}else{target}}

async fn build_long_audio(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,cycle:&Path,cycle_duration:f64,final_duration:f64,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<AudioSource,String>{
  let exact=job.settings.duration_mode!="whole-track"||final_duration<=job.settings.duration_hours*3600.0+0.2;
  if !exact{
    emit_progress(app,job,started,timer,62.0,"Аудио-цикл готов — без лишней многочасовой копии",encoder,attempt,None);
    return Ok(AudioSource::Loop(cycle.to_path_buf()));
  }
  let out=work.join("audio-long.m4a");
  if final_duration>4.0{
    let prefix=work.join("audio-prefix.m4a");let tail=work.join("audio-tail.m4a");let prefix_len=final_duration-3.0;
    let a1=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-i",cycle.to_string_lossy().as_ref(),"-t",&prefix_len.to_string(),"-c:a","copy","-progress","pipe:1","-y",prefix.to_string_lossy().as_ref()].into_iter().map(String::from).collect();run_ffmpeg(app,job,started,timer,a1,"Собираю длинный аудио-кэш",56.0,6.0,prefix_len,encoder,attempt,cancel).await?;
    let offset=(prefix_len%cycle_duration.max(0.1)).max(0.0);let audio_encoder=choose_audio_encoder(app).await;let mut a2:Vec<String>=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&offset.to_string(),"-i",cycle.to_string_lossy().as_ref(),"-t","3","-af","afade=t=out:st=0:d=3"].into_iter().map(String::from).collect();a2.extend(audio_encoder_args(&audio_encoder));a2.extend(vec!["-y",tail.to_string_lossy().as_ref()].into_iter().map(String::from));output(app,"ffmpeg",a2).await?;
    let list=work.join("audio-concat.txt");std::fs::write(&list,format!("file '{}'\nfile '{}'\n",prefix.to_string_lossy().replace('\\',"/"),tail.to_string_lossy().replace('\\',"/"))).map_err(|e|e.to_string())?;let a3=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-c:a","copy","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();output(app,"ffmpeg",a3).await?;
  }else{
    let a=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-i",cycle.to_string_lossy().as_ref(),"-t",&final_duration.to_string(),"-c:a","copy","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();run_ffmpeg(app,job,started,timer,a,"Собираю длинный аудио-кэш",56.0,6.0,final_duration,encoder,attempt,cancel).await?;
  }
  Ok(AudioSource::Long(out))
}

async fn subscribe_events(app:&AppHandle,subs:&[SubscribePreset],final_duration:f64)->Vec<SubEvent>{
  let mut events=Vec::new();
  for s in subs.iter().filter(|s|s.effect.enabled&&!s.effect.source.trim().is_empty()){
    let d=probe_duration(app,&s.effect.source).await.unwrap_or(5.0).max(0.1);let mut starts=Vec::new();
    for x in [s.first_at_sec,s.second_at_sec]{if x>=0.0&&x<final_duration&&!starts.iter().any(|v:&f64|(*v-x).abs()<0.01){starts.push(x)}}
    if s.repeat_every_sec>0.1{let mut x=s.second_at_sec.max(s.first_at_sec)+s.repeat_every_sec;while x<final_duration{starts.push(x);x+=s.repeat_every_sec;if starts.len()>10000{break}}}
    for start in starts{events.push(SubEvent{start,end:(start+d).min(final_duration),sub:s.clone(),event_start:start});}
  }
  events.sort_by(|a,b|a.start.partial_cmp(&b.start).unwrap_or(std::cmp::Ordering::Equal));events
}

fn timed_effects(effects:&[EffectPreset],final_duration:f64)->bool{effects.iter().any(|e|e.enabled&&(e.start_sec>0.01||e.end_sec.map(|x|x<final_duration-0.01).unwrap_or(false)))}

async fn copy_segment(app:&AppHandle,job:&QueueJob,variant:&Path,variant_duration:f64,start:f64,len:f64,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,base:f64,span:f64,started:i64,timer:&Instant)->Result<(),String>{
  let phase=(start%variant_duration.max(0.1)).max(0.0);let args=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&phase.to_string(),"-i",variant.to_string_lossy().as_ref(),"-t",&len.to_string(),"-an","-c:v","copy","-avoid_negative_ts","make_zero","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();run_ffmpeg(app,job,started,timer,args,"Собираю визуальные сегменты",base,span,len,encoder,attempt,cancel).await
}

async fn render_sub_segment(app:&AppHandle,job:&QueueJob,variant:&Path,variant_duration:f64,start:f64,len:f64,active:&[SubEvent],out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,base:f64,span:f64,started:i64,timer:&Instant)->Result<(),String>{
  let phase=(start%variant_duration.max(0.1)).max(0.0);let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&phase.to_string(),"-i",variant.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  for ev in active{let offset=(start-ev.event_start).max(0.0);args.extend(vec!["-ss",&offset.to_string(),"-i",ev.sub.effect.source.as_str()].into_iter().map(String::from));}
  let sub_effects=active.iter().map(|e|e.sub.effect.clone()).collect::<Vec<_>>();let (graph,last)=apply_effects_filter("[0:v]setpts=PTS-STARTPTS[b0]".into(),"b0".into(),&sub_effects,&job.settings,1);let graph=format!("{graph};[{last}]format=yuv420p[outv]");
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t",&len.to_string(),"-an"].into_iter().map(String::from));args.extend(encoder_args(encoder,&job.settings,false));args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));run_ffmpeg(app,job,started,timer,args,"Добавляю Subscribe",base,span,len,encoder,attempt,cancel).await
}

async fn assemble_visual(app:&AppHandle,job:&QueueJob,source_master:&Path,master_duration:f64,effects:&[EffectPreset],subs:&[SubscribePreset],final_duration:f64,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<VisualSource,String>{
  let mark=Instant::now();let events=subscribe_events(app,subs,final_duration).await;let has_timed=timed_effects(effects,final_duration);
  let mut variants:HashMap<String,(PathBuf,f64)>=HashMap::new();
  let initial=active_effects_at(effects,0.001,final_duration);let key=state_key(&initial);let p=build_variant(app,job,source_master,master_duration,&initial,work,encoder,attempt,cancel,0,started,timer).await?;variants.insert(key.clone(),(p,master_duration));
  if events.is_empty()&&!has_timed{emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());return Ok(VisualSource::Loop(variants.get(&key).unwrap().0.clone()))}
  let mut boundaries=vec![0.0,final_duration];for e in effects.iter().filter(|e|e.enabled){if e.start_sec>0.0&&e.start_sec<final_duration{boundaries.push(e.start_sec)}if let Some(x)=e.end_sec{if x>0.0&&x<final_duration{boundaries.push(x)}}}for e in &events{boundaries.push(e.start);boundaries.push(e.end)}
  boundaries.sort_by(|a,b|a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));boundaries.dedup_by(|a,b|(*a-*b).abs()<0.001);
  let intervals=boundaries.windows(2).filter(|w|w[1]-w[0]>0.005).map(|w|(w[0],w[1])).collect::<Vec<_>>();let mut segments=Vec::new();
  for (i,(a,b)) in intervals.iter().copied().enumerate(){if cancel.load(Ordering::SeqCst){return Err(CANCELLED.into())}let mid=(a+b)/2.0;let active_fx=active_effects_at(effects,mid,final_duration);let k=state_key(&active_fx);
    if !variants.contains_key(&k){let no=variants.len();let v=build_variant(app,job,source_master,master_duration,&active_fx,work,encoder,attempt,cancel,no,started,timer).await?;variants.insert(k.clone(),(v,master_duration));}
    let (variant,vd)=variants.get(&k).cloned().unwrap();let active_sub=events.iter().filter(|e|e.start<=mid&&e.end>mid).cloned().collect::<Vec<_>>();let seg=work.join(format!("visual-seg-{i:04}.mp4"));let base=64.0+(i as f64/intervals.len().max(1) as f64)*22.0;let span=22.0/intervals.len().max(1) as f64;
    if active_sub.is_empty(){copy_segment(app,job,&variant,vd,a,b-a,&seg,encoder,attempt,cancel,base,span,started,timer).await?;}else{render_sub_segment(app,job,&variant,vd,a,b-a,&active_sub,&seg,encoder,attempt,cancel,base,span,started,timer).await?;}segments.push(seg);
  }
  let long=work.join("video-long.mp4");let list=work.join("visual-concat.txt");let text=segments.iter().map(|p|format!("file '{}'",p.to_string_lossy().replace('\\',"/"))).collect::<Vec<_>>().join("\n");std::fs::write(&list,text).map_err(|e|e.to_string())?;let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-an","-c:v","copy","-progress","pipe:1","-y",long.to_string_lossy().as_ref()].into_iter().map(String::from).collect();run_ffmpeg(app,job,started,timer,args,"Склеиваю визуальную дорожку",86.0,4.0,final_duration,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());Ok(VisualSource::Long(long))
}

fn write_side_files(job:&QueueJob,output_dir:&Path,durations:&[f64],final_duration:f64,result_stem:&str)->Result<(),String>{
  let name=safe_name(result_stem);let time_dir=output_dir.join("timecodes");let log_dir=output_dir.join("logs");std::fs::create_dir_all(&time_dir).map_err(|e|e.to_string())?;std::fs::create_dir_all(&log_dir).map_err(|e|e.to_string())?;
  let mut t=0.0;let mut i=0usize;let cf=job.settings.crossfade_sec.max(0.0);let mut tc=String::new();while t<final_duration-0.1{let path=&job.project.audio[i%job.project.audio.len()];let title=Path::new(path).file_stem().and_then(|x|x.to_str()).unwrap_or("Track");tc.push_str(&format!("{} {}\n",fmt_ts(t),title));let d=durations[i%durations.len()];t+=(d-if i>0{cf}else{0.0}).max(0.1);i+=1;if i>10000{break}}
  std::fs::write(time_dir.join(format!("{} — timecodes.txt",name)),tc).map_err(|e|e.to_string())?;let tracklist=job.project.audio.iter().enumerate().map(|(i,p)|format!("{}. {}",i+1,Path::new(p).file_name().and_then(|x|x.to_str()).unwrap_or(p))).collect::<Vec<_>>().join("\n");std::fs::write(output_dir.join(format!("{} — tracklist.txt",name)),tracklist).map_err(|e|e.to_string())?;std::fs::write(log_dir.join(format!("{} — project.json",name)),serde_json::to_vec_pretty(job).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;Ok(())
}

async fn verify_result(app:&AppHandle,out:&Path,expected:f64,s:&RenderSettings)->Result<(),String>{let d=probe_duration(app,out.to_string_lossy().as_ref()).await?;if (d-expected).abs()>4.0{return Err(format!("Финальный файл имеет неверную длительность: {:0.1} сек вместо {:0.1}",d,expected))}if !probe_has_audio(app,out).await{return Err("В финальном файле отсутствует аудиодорожка".into())}let args=vec!["-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0:s=x",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();let (stdout,_)=output(app,"ffprobe",args).await?;let got=String::from_utf8_lossy(&stdout);if !got.trim().starts_with(&format!("{}x{}",s.width,s.height)){return Err(format!("Неверное разрешение результата: {}",got.trim()))}Ok(())}

pub async fn render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<(),String>{
  for p in &job.project.media{if !Path::new(p).is_file(){return Err(format!("Не найден файл изображения/видео: {}",Path::new(p).file_name().and_then(|x|x.to_str()).unwrap_or(p)));}}
  for p in &job.project.audio{if !Path::new(p).is_file(){return Err(format!("Не найден аудиофайл: {}",Path::new(p).file_name().and_then(|x|x.to_str()).unwrap_or(p)));}}
  if let Some(p)=job.ambient.as_ref().filter(|x|!x.trim().is_empty()){if !Path::new(p).is_file(){return Err(format!("Не найден ambient-файл: {}",Path::new(p).file_name().and_then(|x|x.to_str()).unwrap_or(p)));}}
  let started=chrono::Utc::now().timestamp_millis();let timer=Instant::now();let mut last_error=String::new();let out_dir=PathBuf::from(&job.settings.output_dir);std::fs::create_dir_all(&out_dir).map_err(|e|e.to_string())?;let out=unique_output(&out_dir,&job.project.name);
  for attempt in 1..=2{
    if cancel.load(Ordering::SeqCst){return Err(CANCELLED.into())}let _=std::fs::remove_file(&out);let encoder=choose_encoder(app,&job.settings).await;let pure_static=job.project.media.iter().all(|m|is_image(m))&&job.effects.iter().all(|e|!e.enabled)&&job.subscribes.iter().all(|e|!e.effect.enabled);let _=app.emit("engine-profile",json!({"id":job.project.id,"smartSize":pure_static,"targetVideoKbps":if pure_static{Some(static_video_kbps(&job.settings))}else{None::<u64>}}));emit_progress(app,job,started,&timer,1.0,"Анализ файлов",&encoder,attempt,None);let work=std::env::temp_dir().join(format!("endlume-{}-{}",job.project.id,attempt));let _=std::fs::remove_dir_all(&work);std::fs::create_dir_all(&work).map_err(|e|e.to_string())?;
    let result:Result<(Vec<f64>,f64),String>=async{
      emit_progress(app,job,started,&timer,4.0,"Проверяю самый быстрый движок",&encoder,attempt,None);let (source_master,master_duration)=build_source_master(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;let (fx,subs)=prepare_overlays(app,job,started,&timer,&encoder,attempt).await?;let (cycle,durations,cycle_duration)=build_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;let target=job.settings.duration_hours*3600.0;let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,&job.settings.duration_mode);let audio=build_long_audio(app,job,started,&timer,&work,&cycle,cycle_duration,final_duration,&encoder,attempt,&cancel).await?;
      let visual=assemble_visual(app,job,&source_master,master_duration,&fx,&subs,final_duration,&work,&encoder,attempt,&cancel,started,&timer).await?;let mux_mark=Instant::now();let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();match visual{VisualSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),VisualSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}match audio{AudioSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));run_ffmpeg(app,job,started,&timer,args,"Собираю итоговое видео",90.0,6.0,final_duration,&encoder,attempt,&cancel).await?;emit_timing(app,&job.project.id,"final-mux",mux_mark.elapsed().as_secs_f64());emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&encoder,attempt,None);verify_result(app,&out,final_duration,&job.settings).await?;let result_stem=out.file_stem().and_then(|x|x.to_str()).unwrap_or(&job.project.name);write_side_files(job,&out_dir,&durations,final_duration,result_stem)?;Ok((durations,final_duration))
    }.await;
    match result{
      Ok((_durations,_fd))=>{let bytes=std::fs::metadata(&out).ok().map(|m|m.len());let bitrate=probe_video_bitrate(app,&out).await;let _=app.emit("render-done",Progress{id:job.project.id.clone(),status:"done".into(),progress:100.0,stage:"Готово".into(),started_at:Some(started),elapsed_sec:timer.elapsed().as_secs_f64(),eta_sec:Some(0.0),result_path:Some(out.to_string_lossy().into_owned()),result_bytes:bytes,actual_video_bitrate:bitrate,cpu_pct:None,ram_bytes:None,ram_total_bytes:None,ram_available_bytes:None,gpu_pct:None,encoder:Some(encoder),attempt:Some(attempt)});let _=std::fs::remove_dir_all(&work);return Ok(())},
      Err(e)=>{last_error=e;let _=std::fs::remove_dir_all(&work);let _=std::fs::remove_file(&out);if last_error==CANCELLED{return Err(last_error)}if attempt<2{emit_progress(app,job,started,&timer,2.0,"Проверка не пройдена — автоматический повтор",&encoder,attempt+1,None);}}
    }
  }
  Err(last_error)
}
