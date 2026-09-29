use crate::{cache,model::{EffectPreset,Progress,QueueJob,RenderSettings,SubscribePreset}};
use serde_json::json;
use std::{collections::HashMap,path::{Path,PathBuf},process::Command,sync::{Arc,OnceLock,atomic::{AtomicBool,AtomicU64,Ordering}},time::{Duration,Instant,UNIX_EPOCH}};
use sysinfo::{Pid,ProcessesToUpdate,System};
use tauri::{AppHandle,Emitter,Manager};
use tauri_plugin_shell::{process::CommandEvent,ShellExt};

const IMAGE_EXT:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];
const CANCELLED:&str="__ENDLUME_CANCELLED__";
const LICENSE_BLOCKED:&str="__ENDLUME_LICENSE_BLOCKED__";
fn ensure_license_allowed()->Result<(),String>{if crate::license::production_blocked(){Err(LICENSE_BLOCKED.into())}else{Ok(())}}
static ENCODER_CACHE:OnceLock<parking_lot::Mutex<HashMap<String,String>>>=OnceLock::new();
static ENCODER_FINGERPRINT:OnceLock<String>=OnceLock::new();
static AUDIO_ENCODER_CACHE:OnceLock<String>=OnceLock::new();
static AUDIO_PROBE_CACHE:OnceLock<parking_lot::Mutex<HashMap<String,AudioProbe>>>=OnceLock::new();
static FFMPEG_LAUNCHES:AtomicU64=AtomicU64::new(0);
static FFPROBE_LAUNCHES:AtomicU64=AtomicU64::new(0);

#[derive(Clone,Debug)]
struct AudioProbe{codec:String,sample_rate:u32,channels:u32,duration:f64}

#[derive(Clone)]
struct SubEvent{start:f64,end:f64,sub:SubscribePreset,event_start:f64}

enum VisualSource{Loop(PathBuf),Long(PathBuf),Concat(PathBuf)}
enum AudioSource{Loop(PathBuf),Long(PathBuf),ConcatList(PathBuf)}

#[derive(Clone,Debug)]
pub struct RenderOutcome{
  pub output_path:String,
  pub output_bytes:Option<u64>,
  pub encoder:String,
  pub final_video_duration_seconds:f64,
  pub fast_path:bool,
  pub fast_path_reason:String,
  pub audio_mode:String,
  pub video_codec:String,
  pub audio_codec:String,
}

fn is_image(path:&str)->bool{Path::new(path).extension().and_then(|x|x.to_str()).map(|x|IMAGE_EXT.contains(&x.to_ascii_lowercase().as_str())).unwrap_or(false)}
pub(crate) fn is_image_for_telemetry(path:&str)->bool{is_image(path)}
fn safe_name(name:&str)->String{name.chars().map(|c|if ['/', '\\', ':', '*', '?', '"', '<', '>', '|'].contains(&c){'_'}else{c}).collect()}
fn unique_output(dir:&Path,name:&str)->PathBuf{let safe=safe_name(name);let mut p=dir.join(format!("{} — Ready Videos.mp4",safe));let mut n=2;while p.exists(){p=dir.join(format!("{} — Ready Videos_{}.mp4",safe,n));n+=1}p}
fn unique_output_ext(dir:&Path,name:&str,ext:&str)->PathBuf{let safe=safe_name(name);let ext=ext.trim_start_matches('.');let mut p=dir.join(format!("{} — Ready Videos.{}",safe,ext));let mut n=2;while p.exists(){p=dir.join(format!("{} — Ready Videos_{}.{}",safe,n,ext));n+=1}p}
fn fmt_ts(sec:f64)->String{let s=sec.max(0.0).round() as u64;format!("{:02}:{:02}:{:02}",s/3600,(s%3600)/60,s%60)}
fn color_ffmpeg(hex:&str)->String{format!("0x{}",hex.trim().trim_start_matches('#').trim_start_matches("0x"))}
fn emit_timing(app:&AppHandle,id:&str,key:&str,sec:f64){let _=app.emit("engine-timing",json!({"id":id,"key":key,"seconds":sec}));}
fn diag_line(value:serde_json::Value){eprintln!("ENDLUME_DIAG {}",value);}
fn encoder_class(encoder:&str)->&'static str{if matches!(encoder,"hevc_videotoolbox"|"hevc_nvenc"|"hevc_qsv"|"hevc_amf"|"h264_videotoolbox"|"h264_nvenc"|"h264_qsv"|"h264_amf"){"hardware"}else{"software"}}


const AUDIO_EXT:&[&str]=&["mp3","wav","m4a","aac","flac","ogg","opus","aif","aiff"];
fn is_audio(path:&Path)->bool{path.extension().and_then(|x|x.to_str()).map(|x|AUDIO_EXT.contains(&x.to_ascii_lowercase().as_str())).unwrap_or(false)}
fn software_encoder(s:&RenderSettings)->String{if s.codec.eq_ignore_ascii_case("h265"){"libx265".into()}else{"libx264".into()}}

#[derive(Clone,Copy,Debug)]
pub(crate) struct FastPathDecision{pub eligible:bool,pub reason:&'static str}

fn audio_processing_requested(job:&QueueJob)->bool{
  job.settings.crossfade_sec>0.01||job.settings.normalize_lufs||job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false)
}

pub(crate) fn fast_path_decision(job:&QueueJob)->FastPathDecision{
  if job.project.media.is_empty(){return FastPathDecision{eligible:false,reason:"DISQUALIFIED_NO_MEDIA"}}
  let all_images=job.project.media.iter().all(|m|is_image(m));
  if all_images{
    if job.project.media.len()==1{return FastPathDecision{eligible:true,reason:"FAST_ONE_IMAGE"}}
    if job.effects.iter().any(|e|e.enabled&&!e.source.trim().is_empty()){return FastPathDecision{eligible:false,reason:"DISQUALIFIED_MULTI_STILL_EFFECTS"}}
    if job.subscribes.iter().any(|x|x.effect.enabled&&!x.effect.source.trim().is_empty()){return FastPathDecision{eligible:false,reason:"DISQUALIFIED_MULTI_STILL_SUBSCRIBE"}}
    return FastPathDecision{eligible:true,reason:"FAST_MULTI_STILL"}
  }
  if job.project.media.len()==1{return FastPathDecision{eligible:false,reason:"DISQUALIFIED_SHORT_VIDEO_LOOP_UNSUPPORTED"}}
  FastPathDecision{eligible:false,reason:"DISQUALIFIED_MULTIPLE_MEDIA"}
}
fn smart_repeat_project(job:&QueueJob)->bool{fast_path_decision(job).eligible}
fn fast_multi_still(job:&QueueJob)->bool{
  let reason=fast_path_decision(job).reason;
  if reason=="FAST_MULTI_STILL"{return true}
  if reason!="FAST_ONE_IMAGE"{return false}
  let has_effects=job.effects.iter().any(|e|e.enabled&&!e.source.trim().is_empty());
  let has_subs=job.subscribes.iter().any(|x|x.effect.enabled&&!x.effect.source.trim().is_empty());
  !has_effects&&!has_subs
}

async fn choose_fidelity_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {
    if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}
  }
  #[cfg(target_os="windows")]
  {
    if attempt==1{
      for encoder in ["hevc_nvenc","hevc_qsv","hevc_amf"]{
        if encoder_works(app,encoder).await{return encoder.into()}
      }
    }
  }
  "libx265".into()
}

fn fidelity_video_args(encoder:&str,s:&RenderSettings)->Vec<String>{
  let g=(s.fps.max(1)*10).to_string();
  let raw:Vec<&str>=match encoder{
    "hevc_videotoolbox"=>vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-q:v","95","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"],
    "h264_videotoolbox"=>vec!["-c:v","h264_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-q:v","95","-g",&g,"-pix_fmt","yuv420p"],
    "hevc_nvenc"=>vec!["-c:v","hevc_nvenc","-preset","p4","-rc","vbr","-cq","18","-b:v","0","-maxrate","12M","-bufsize","64M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"],
    "hevc_qsv"=>vec!["-c:v","hevc_qsv","-global_quality","18","-maxrate","12M","-bufsize","64M","-g",&g,"-tag:v","hvc1","-pix_fmt","nv12"],
    "hevc_amf"=>vec!["-c:v","hevc_amf","-quality","balanced","-rc","vbr_peak","-qp_i","18","-maxrate","12M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"],
    "libx265"=>vec!["-c:v","libx265","-preset","ultrafast","-crf","14","-tune","ssim","-g",&g,"-pix_fmt","yuv420p"],
    _=>vec!["-c:v","libx264","-preset","ultrafast","-crf","12","-tune","stillimage","-g",&g,"-keyint_min",&g,"-sc_threshold","0","-pix_fmt","yuv420p"],
  };
  raw.into_iter().map(String::from).collect()
}

fn hybrid_master_seconds(_s:&RenderSettings)->f64{12.0}

async fn hybrid_master_seconds_for_job(app:&AppHandle,job:&QueueJob)->f64{
  let mut d=hybrid_master_seconds(&job.settings);
  for e in job.effects.iter().filter(|e|e.enabled&&!e.source.trim().is_empty()){
    if let Ok(x)=probe_duration(app,&e.source).await{d=d.max(x.clamp(2.0,60.0));}
  }
  d.clamp(12.0,60.0)
}

fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}

const STRICT_857_MAX_GOP_FRAMES:u32=1800;

fn hybrid_fidelity_args(s:&RenderSettings,encoder:&str,duration:f64)->Vec<String>{
  let frames=(s.fps.max(1) as f64*duration.max(2.0)).round().max(1.0) as u32;
  let hw_g=frames.min(STRICT_857_MAX_GOP_FRAMES).to_string();
  let sw_g=frames.to_string();
  match encoder{
    "libx265"=>{
      let x265=format!("keyint={}:min-keyint={}:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0",sw_g,sw_g);
      vec!["-c:v","libx265","-preset","ultrafast","-crf","18","-maxrate","500k","-bufsize","4M","-x265-params",&x265,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
    },
    "hevc_nvenc"=>vec!["-c:v","hevc_nvenc","-preset","p4","-rc","vbr","-cq","18","-b:v","500k","-maxrate","12M","-bufsize","64M","-g",&hw_g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect(),
    "hevc_qsv"=>vec!["-c:v","hevc_qsv","-global_quality","18","-maxrate","12M","-bufsize","64M","-g",&hw_g,"-tag:v","hvc1","-pix_fmt","nv12"].into_iter().map(String::from).collect(),
    "hevc_amf"=>vec!["-c:v","hevc_amf","-quality","balanced","-rc","vbr_peak","-b:v","500k","-maxrate","12M","-g",&hw_g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect(),
    "hevc_videotoolbox"=>vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M","-g",&hw_g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect(),
    _=>hybrid_fidelity_args(s,"libx265",duration),
  }
}

fn periodic_fidelity_args(s:&RenderSettings,encoder:&str,duration:f64)->Vec<String>{
  // 8.67: retain q100; prio_speed changes hardware scheduling, not source pixels.
  // Short GOP grows real HEVC payload toward the requested size without padding.
  let g="80";
  match encoder{
    "hevc_videotoolbox"=>vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","20M","-bufsize","80M","-g",g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect(),
    "hevc_nvenc"=>vec!["-c:v","hevc_nvenc","-preset","p4","-rc","vbr","-cq","18","-b:v","0","-maxrate","20M","-bufsize","80M","-g",g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect(),
    "hevc_qsv"=>vec!["-c:v","hevc_qsv","-global_quality","18","-maxrate","20M","-bufsize","80M","-g",g,"-tag:v","hvc1","-pix_fmt","nv12"].into_iter().map(String::from).collect(),
    "hevc_amf"=>vec!["-c:v","hevc_amf","-quality","balanced","-rc","vbr_peak","-qp_i","18","-maxrate","20M","-g",g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect(),
    _=>hybrid_fidelity_args(s,encoder,duration),
  }
}

fn encoder_cache_path(app:&AppHandle)->Option<PathBuf>{
  app.path().app_cache_dir().ok().map(|p|p.join("encoder-selection-8.64.json"))
}

fn encoder_hardware_fingerprint()->String{
  ENCODER_FINGERPRINT.get_or_init(||{
    #[cfg(target_os="windows")]
    {
      let gpu=Command::new("powershell.exe")
        .args(["-NoProfile","-NonInteractive","-Command","Get-CimInstance Win32_VideoController | Sort-Object PNPDeviceID | Select-Object Name,DriverVersion,PNPDeviceID | ConvertTo-Json -Compress"])
        .output().ok().filter(|o|o.status.success()).map(|o|String::from_utf8_lossy(&o.stdout).trim().to_string()).unwrap_or_else(||"gpu-query-unavailable".into());
      return format!("windows|{}|{}",std::env::consts::ARCH,gpu)
    }
    #[cfg(not(target_os="windows"))]
    {format!("{}|{}",std::env::consts::OS,std::env::consts::ARCH)}
  }).clone()
}

fn load_persistent_encoder(app:&AppHandle)->Option<String>{
  let path=encoder_cache_path(app)?;
  let raw=std::fs::read(path).ok()?;
  let value:serde_json::Value=serde_json::from_slice(&raw).ok()?;
  if value.get("fingerprint").and_then(|v|v.as_str())?!=encoder_hardware_fingerprint(){return None}
  let selected=value.get("selected").and_then(|v|v.as_str())?.to_string();
  if !matches!(selected.as_str(),"hevc_nvenc"|"hevc_qsv"|"hevc_amf"|"hevc_videotoolbox"|"libx265"){return None}
  Some(selected)
}

fn save_persistent_encoder(app:&AppHandle,selected:&str){
  let Some(path)=encoder_cache_path(app) else{return};
  if let Some(parent)=path.parent(){let _=std::fs::create_dir_all(parent);}
  let payload=json!({"version":"1.0.0-alpha.8.65","fingerprint":encoder_hardware_fingerprint(),"selected":selected});
  let _=std::fs::write(path,serde_json::to_vec(&payload).unwrap_or_default());
}

fn invalidate_hybrid_encoder_cache(app:&AppHandle){
  if let Some(cache)=ENCODER_CACHE.get(){cache.lock().remove("hybrid-hevc");}
  if let Some(path)=encoder_cache_path(app){let _=std::fs::remove_file(path);}
}

async fn fast_encoder_sample(app:&AppHandle,encoder:&str)->Option<f64>{
  let started=Instant::now();
  let args=vec!["-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=black:s=640x360:r=60","-frames:v","30","-an","-c:v",encoder,"-pix_fmt","yuv420p","-f","null","-"].into_iter().map(String::from).collect();
  output(app,"ffmpeg",args).await.ok().map(|_|started.elapsed().as_secs_f64())
}

async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  let cache=ENCODER_CACHE.get_or_init(||parking_lot::Mutex::new(HashMap::new()));
  if attempt==1{
    if let Some(found)=cache.lock().get("hybrid-hevc").cloned(){return found}
    if let Some(found)=load_persistent_encoder(app){
      cache.lock().insert("hybrid-hevc".into(),found.clone());
      return found
    }
    #[cfg(target_os="macos")]
    {
      if fast_encoder_sample(app,"hevc_videotoolbox").await.is_some(){
        let selected="hevc_videotoolbox".to_string();cache.lock().insert("hybrid-hevc".into(),selected.clone());save_persistent_encoder(app,&selected);return selected
      }
    }
    #[cfg(target_os="windows")]
    {
      let mut best:Option<(String,f64)>=None;
      for encoder in ["hevc_nvenc","hevc_qsv","hevc_amf"]{
        if let Some(seconds)=fast_encoder_sample(app,encoder).await{
          if best.as_ref().map(|(_,s)|seconds<*s).unwrap_or(true){best=Some((encoder.to_string(),seconds));}
        }
      }
      if let Some((selected,_))=best{cache.lock().insert("hybrid-hevc".into(),selected.clone());save_persistent_encoder(app,&selected);return selected}
    }
  }
  if encoder_works(app,"libx265").await{let selected="libx265".to_string();if attempt==1{cache.lock().insert("hybrid-hevc".into(),selected.clone());save_persistent_encoder(app,&selected);}return selected}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  "libx265".into()
}

// ENDLUME_WINDOWS_861_STRICT_ENCODERS: keep macOS strict semantics intact while
// allowing the exact 8.61 strict pipeline to use Windows HEVC hardware and x265 fallback.
fn strict_856_encoder_allowed(encoder:&str)->bool{
  #[cfg(target_os="macos")]
  {return encoder=="hevc_videotoolbox"}
  #[cfg(target_os="windows")]
  {return matches!(encoder,"hevc_nvenc"|"hevc_qsv"|"hevc_amf"|"libx265")}
  #[cfg(not(any(target_os="macos",target_os="windows")))]
  {encoder=="libx265"}
}

async fn probe_audio_decodes(app:&AppHandle,path:&Path)->bool{
  let args=vec!["-v","error","-i",path.to_string_lossy().as_ref(),"-map","0:a:0","-t","1.0","-f","null","-"].into_iter().map(String::from).collect();
  output(app,"ffmpeg",args).await.is_ok()
}

fn audio_probe_key(path:&str)->String{
  let meta=std::fs::metadata(path).ok();
  let size=meta.as_ref().map(|m|m.len()).unwrap_or(0);
  let mtime=meta.and_then(|m|m.modified().ok()).and_then(|t|t.duration_since(UNIX_EPOCH).ok()).map(|d|d.as_secs()).unwrap_or(0);
  format!("{path}|{size}|{mtime}")
}

async fn probe_audio_meta(app:&AppHandle,path:&str)->Result<AudioProbe,String>{
  let key=audio_probe_key(path);let cache=AUDIO_PROBE_CACHE.get_or_init(||parking_lot::Mutex::new(HashMap::new()));
  if let Some(found)=cache.lock().get(&key).cloned(){return Ok(found)}
  let args=vec!["-v","error","-select_streams","a:0","-show_entries","stream=codec_name,sample_rate,channels:format=duration","-of","json",path].into_iter().map(String::from).collect();
  let (stdout,_)=output(app,"ffprobe",args).await?;
  let v:serde_json::Value=serde_json::from_slice(&stdout).map_err(|e|format!("FFprobe JSON {path}: {e}"))?;
  let stream=v.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()).ok_or_else(||format!("Не удалось прочитать аудиопоток: {path}"))?;
  let codec=stream.get("codec_name").and_then(|x|x.as_str()).unwrap_or("").to_string();
  let sample_rate=stream.get("sample_rate").and_then(|x|x.as_str()).and_then(|x|x.parse::<u32>().ok()).unwrap_or(0);
  let channels=stream.get("channels").and_then(|x|x.as_u64()).unwrap_or(0) as u32;
  let duration=v.get("format").and_then(|x|x.get("duration")).and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok()).unwrap_or(0.0).max(0.2);
  if codec.is_empty()||sample_rate==0||channels==0{return Err(format!("Не удалось прочитать параметры аудио: {path}"))}
  let meta=AudioProbe{codec,sample_rate,channels,duration};cache.lock().insert(key,meta.clone());Ok(meta)
}

fn ffconcat_escape(path:&Path)->String{
  let s=path.to_string_lossy().replace('\\',"/");
  let mut out=String::with_capacity(s.len()+8);
  for c in s.chars(){
    if matches!(c,' '|'\''|'#'){out.push('\\')}
    out.push(c);
  }
  out
}

async fn probe_original_audio_batch(app:&AppHandle,paths:&[String])->Result<Vec<AudioProbe>,String>{
  const PARALLEL_PROBES:usize=4;
  let mut metas=Vec::with_capacity(paths.len());
  for chunk in paths.chunks(PARALLEL_PROBES){
    let mut tasks=Vec::with_capacity(chunk.len());
    for path in chunk{
      let app=app.clone();let path=path.clone();
      tasks.push(tauri::async_runtime::spawn(async move{probe_audio_meta(&app,&path).await}));
    }
    for task in tasks{
      let meta=task.await.map_err(|e|format!("Audio probe task failed: {e}"))??;
      metas.push(meta);
    }
  }
  Ok(metas)
}

async fn build_original_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
  if job.project.audio.is_empty(){return Err("Нет песен".into())}
  let probe_mark=Instant::now();let mut durations=Vec::with_capacity(job.project.audio.len());let mut first:Option<(String,u32,u32)>=None;
  for a in &job.project.audio{if !a.to_ascii_lowercase().ends_with(".mp3"){return Err(format!("{} — не MP3",Path::new(a).file_name().and_then(|x|x.to_str()).unwrap_or(a)))}}
  let metas=probe_original_audio_batch(app,&job.project.audio).await?;
  for (a,meta) in job.project.audio.iter().zip(metas.into_iter()){
    if meta.codec!="mp3"{return Err(format!("{} — codec {}",Path::new(a).file_name().and_then(|x|x.to_str()).unwrap_or(a),meta.codec))}
    let sig=(meta.codec.clone(),meta.sample_rate,meta.channels);
    if let Some(ref base)=first{if base!=&sig{return Err(format!("MP3 имеют разные параметры: ожидается {} Hz / {} ch, найдено {} Hz / {} ch",base.1,base.2,sig.1,sig.2))}}else{first=Some(sig)}
    durations.push(meta.duration);
  }
  let probe_seconds=probe_mark.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"probe",probe_seconds);emit_timing(app,&job.project.id,"audio-probe",probe_seconds);
  let expected=durations.iter().sum::<f64>().max(0.2);
  let prep_mark=Instant::now();let direct_list=work.join("audio-direct-list.txt");
  let direct_body=job.project.audio.iter().map(|p|format!("file {}",ffconcat_escape(Path::new(p)))).collect::<Vec<_>>().join("\n");
  std::fs::write(&direct_list,direct_body).map_err(|e|e.to_string())?;
  // 8.64: do not physically copy the whole playlist before the final MP4 mux.
  // Validate the concat demuxer on a tiny packet-copy sample, then feed the list itself
  // into the final mux with -stream_loop -1. This removes one O(audio_bytes) write+read.
  let direct_probe=work.join("audio-direct-probe.mp3");
  let probe_len=expected.min(12.0).max(1.0);
  let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",direct_list.to_string_lossy().as_ref(),"-t",&probe_len.to_string(),"-map","0:a:0","-c:a","copy","-map_metadata","-1","-write_xing","0","-id3v2_version","0","-y",direct_probe.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  let direct=output(app,"ffmpeg",args).await;
  if direct.is_ok()&&probe_audio_decodes(app,&direct_probe).await{
    let _=std::fs::remove_file(&direct_probe);
    emit_timing(app,&job.project.id,"audio-preparation",prep_mark.elapsed().as_secs_f64());
    return Ok((direct_list,durations,expected))
  }

  emit_warning(app,&job.project.id,"Direct MP3 concat list не прошёл integrity gate; использую безопасный packet-copy clean-remux fallback.");
  let mut clean=Vec::with_capacity(job.project.audio.len());let remux_mark=Instant::now();
  for (i,a) in job.project.audio.iter().enumerate(){
    let dst=work.join(format!("audio-clean-{i:03}.mp3"));
    let args=vec!["-hide_banner","-loglevel","error","-i",a.as_str(),"-map","0:a:0","-c:a","copy","-map_metadata","-1","-write_xing","0","-id3v2_version","0","-y",dst.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
    output(app,"ffmpeg",args).await.map_err(|e|format!("Original Audio clean-remux: {e}"))?;clean.push(dst);
  }
  emit_timing(app,&job.project.id,"audio-clean-remux",remux_mark.elapsed().as_secs_f64());
  let fallback_list=work.join("audio-clean-list.txt");
  let fallback_body=clean.iter().map(|p|format!("file {}",ffconcat_escape(p))).collect::<Vec<_>>().join("\n");std::fs::write(&fallback_list,fallback_body).map_err(|e|e.to_string())?;
  let fallback=work.join("audio-original-clean.mp3");
  let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",fallback_list.to_string_lossy().as_ref(),"-map","0:a:0","-c:a","copy","-map_metadata","-1","-write_xing","0","-id3v2_version","0","-progress","pipe:1","-y",fallback.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  run_ffmpeg(app,job,started,timer,args,"Original Audio: safe MP3 packet-copy fallback",35.0,8.0,expected,encoder,attempt,cancel).await?;
  if !probe_audio_decodes(app,&fallback).await{return Err("Original Audio: MP3 packet-copy fallback не декодируется".into())}
  let cycle_duration=probe_duration(app,fallback.to_string_lossy().as_ref()).await.unwrap_or(expected);
  emit_timing(app,&job.project.id,"audio-preparation",prep_mark.elapsed().as_secs_f64());
  Ok((fallback,durations,cycle_duration))
}

async fn build_lossless_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
  if job.project.audio.is_empty(){return Err("Нет песен".into())}
  let mut durations=Vec::new();let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
  for a in &job.project.audio{
    durations.push(probe_duration(app,a).await.unwrap_or(180.0).max(0.2));
    args.extend(vec!["-i",a.as_str()].into_iter().map(String::from));
  }
  let mut graph=String::new();
  for i in 0..job.project.audio.len(){
    if i>0{graph.push(';')}
    graph.push_str(&format!("[{i}:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a{i}]"));
  }
  let inputs=(0..job.project.audio.len()).map(|i|format!("[a{i}]")).collect::<String>();
  graph.push_str(&format!(";{inputs}concat=n={}:v=0:a=1[outa]",job.project.audio.len()));
  let cycle=work.join("audio-lossless.m4a");let expected=durations.iter().sum::<f64>().max(0.2);
  args.extend(vec!["-filter_complex",&graph,"-map","[outa]","-c:a","alac","-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"Original Audio: ALAC lossless fallback",35.0,12.0,expected,encoder,attempt,cancel).await?;
  let cycle_duration=probe_duration(app,cycle.to_string_lossy().as_ref()).await.unwrap_or(expected);
  Ok((cycle,durations,cycle_duration))
}
fn emit_warning(app:&AppHandle,id:&str,message:&str){let _=app.emit("render-warning",json!({"id":id,"message":message}));}

fn writable_dir(path:&Path)->bool{
  if std::fs::create_dir_all(path).is_err(){return false}
  let probe=path.join(format!(".endlume-write-test-{}",uuid::Uuid::new_v4()));
  match std::fs::write(&probe,b"ok"){Ok(_)=>{let _=std::fs::remove_file(probe);true},Err(_)=>false}
}

fn resolve_output_dir(app:&AppHandle,requested:&Path)->Result<PathBuf,String>{
  if !requested.as_os_str().is_empty()&&writable_dir(requested){return Ok(requested.to_path_buf())}
  let fallback=app.path().video_dir().map_err(|e|format!("Не удалось определить папку Movies: {e}"))?.join("ENDLUME Studio");
  if writable_dir(&fallback){Ok(fallback)}else{Err("ENDLUME не может записать ни в выбранную папку, ни в Movies/ENDLUME Studio".into())}
}

fn render_work_dir(app:&AppHandle,id:&str,attempt:u32)->Result<PathBuf,String>{
  let base=app.path().app_cache_dir().unwrap_or_else(|_|std::env::temp_dir().join("studio.endlume.desktop"));
  let root=base.join("render-work");
  std::fs::create_dir_all(&root).map_err(|e|format!("Не удалось создать локальную рабочую папку ENDLUME: {e}"))?;
  let dir=root.join(format!("{}-{}",safe_name(id),attempt));
  let _=std::fs::remove_dir_all(&dir);
  std::fs::create_dir_all(&dir).map_err(|e|format!("Не удалось создать локальную рабочую папку проекта: {e}"))?;
  Ok(dir)
}

fn finalize_local_output(src:&Path,out:&Path)->Result<(),String>{
  let total_mark=Instant::now();let parent=out.parent().ok_or_else(||"8.61: у итогового файла нет родительской папки".to_string())?;
  std::fs::create_dir_all(parent).map_err(|e|format!("8.61: не удалось создать папку результата: {e}"))?;
  let part=parent.join(format!(".{}.endlume-part",out.file_name().and_then(|x|x.to_str()).unwrap_or("render.mov")));
  let _=std::fs::remove_file(&part);let rename_mark=Instant::now();let mut mode="rename";let mut copy_seconds=0.0;let mut fsync_seconds=0.0;let mut copied_bytes=0u64;
  match std::fs::rename(src,&part){
    Ok(_)=>{},
    Err(_)=>{
      mode="copy";let mut input=std::fs::File::open(src).map_err(|e|format!("8.61: не удалось открыть локальный результат: {e}"))?;
      let mut output=std::fs::File::create(&part).map_err(|e|format!("8.61: не удалось создать временный итоговый файл: {e}"))?;
      let copy_mark=Instant::now();copied_bytes=std::io::copy(&mut input,&mut output).map_err(|e|format!("8.61: не удалось перенести итоговое видео на выбранный диск: {e}"))?;copy_seconds=copy_mark.elapsed().as_secs_f64();
      let fsync_mark=Instant::now();output.sync_all().map_err(|e|format!("8.61: не удалось синхронизировать итоговое видео: {e}"))?;fsync_seconds=fsync_mark.elapsed().as_secs_f64();
      drop(output);let _=std::fs::remove_file(src);
    }
  }
  let initial_rename_seconds=rename_mark.elapsed().as_secs_f64();let _=std::fs::remove_file(out);let final_rename_mark=Instant::now();
  std::fs::rename(&part,out).map_err(|e|format!("8.63: не удалось атомарно завершить итоговый MP4: {e}"))?;
  diag_line(json!({"kind":"finalize-output","mode":mode,"src":src,"out":out,"copiedBytes":copied_bytes,"initialRenameOrCopySeconds":initial_rename_seconds,"copySeconds":copy_seconds,"fsyncSeconds":fsync_seconds,"finalRenameSeconds":final_rename_mark.elapsed().as_secs_f64(),"totalSeconds":total_mark.elapsed().as_secs_f64()}));
  Ok(())
}


fn refresh_project_paths(job:&mut QueueJob){
  let root=PathBuf::from(&job.project.path);
  if root.is_dir(){
    let media_missing=job.project.media.is_empty()||job.project.media.iter().any(|p|!Path::new(p).is_file());
    let audio_missing=job.project.audio.is_empty()||job.project.audio.iter().any(|p|!Path::new(p).is_file());
    if media_missing{
      let mut files=walkdir::WalkDir::new(&root).max_depth(2).into_iter().filter_map(Result::ok).map(|e|e.into_path()).filter(|p|p.is_file()&&is_image(p.to_string_lossy().as_ref())).collect::<Vec<_>>();
      files.sort_by_key(|p|p.file_name().map(|x|x.to_string_lossy().to_lowercase()).unwrap_or_default());
      if !files.is_empty(){job.project.media=files.into_iter().map(|p|p.to_string_lossy().into_owned()).collect();}
    }
    if audio_missing{
      let mut files=walkdir::WalkDir::new(&root).max_depth(2).into_iter().filter_map(Result::ok).map(|e|e.into_path()).filter(|p|p.is_file()&&is_audio(p)).collect::<Vec<_>>();
      files.sort_by_key(|p|p.file_name().map(|x|x.to_string_lossy().to_lowercase()).unwrap_or_default());
      if !files.is_empty(){job.project.audio=files.into_iter().map(|p|p.to_string_lossy().into_owned()).collect();}
    }
  }
  if job.ambient.as_ref().map(|p|!p.trim().is_empty()&&!Path::new(p).is_file()).unwrap_or(false){job.ambient=None;}
}

async fn output(app:&AppHandle,name:&str,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{
  let launch=if name=="ffmpeg"{FFMPEG_LAUNCHES.fetch_add(1,Ordering::Relaxed)+1}else if name=="ffprobe"{FFPROBE_LAUNCHES.fetch_add(1,Ordering::Relaxed)+1}else{0};
  let argv=args.clone();let mark=Instant::now();
  let result=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string());
  let seconds=mark.elapsed().as_secs_f64();
  match result{
    Ok(out)=>{
      diag_line(json!({"kind":"tool-call","tool":name,"launch":launch,"seconds":seconds,"success":out.status.success(),"args":argv}));
      if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
      Ok((out.stdout,out.stderr))
    },
    Err(e)=>{diag_line(json!({"kind":"tool-call","tool":name,"launch":launch,"seconds":seconds,"success":false,"args":argv,"error":e}));Err(e)}
  }
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
    0..=1920=>520,
    1921..=2560=>600,
    _=>700,
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
  args.extend(fidelity_video_args(encoder,s));
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
  let elapsed=timer.elapsed().as_secs_f64();
  let raw_eta=if progress>1.0{Some(elapsed*(100.0-progress)/progress)}else{None};
  // Fast-path progress is phase-based (short master -> audio -> manifest -> verify), not proportional
  // to the multi-hour final media duration. Never extrapolate it into a multi-minute fake ETA.
  let eta=if smart_repeat_project(job)&&!audio_processing_requested(job){raw_eta.map(|v|v.min(30.0))}else{raw_eta};
  let (cpu,ram,total,available)=metrics.unwrap_or((0.0,0,0,0));
  let _=app.emit("render-progress",Progress{id:job.project.id.clone(),status:"rendering".into(),progress:progress.clamp(0.0,99.9),stage:stage.into(),started_at:Some(started),elapsed_sec:elapsed,eta_sec:eta,result_path:None,result_bytes:None,actual_video_bitrate:None,cpu_pct:metrics.map(|_|cpu),ram_bytes:metrics.map(|_|ram),ram_total_bytes:metrics.map(|_|total),ram_available_bytes:metrics.map(|_|available),gpu_pct:None,encoder:Some(encoder.into()),attempt:Some(attempt)});
  crate::license::telemetry_render_progress(job,progress.clamp(0.0,99.9),eta,stage,encoder);
}

async fn run_ffmpeg(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,args:Vec<String>,stage:&str,base:f64,span:f64,expected_sec:f64,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(),String>{
  let launch=FFMPEG_LAUNCHES.fetch_add(1,Ordering::Relaxed)+1;
  let argv=args.clone();let process_mark=Instant::now();
  emit_progress(app,job,started,timer,base,stage,encoder,attempt,None);
  let spawn_mark=Instant::now();
  let (mut rx,child)=app.shell().sidecar("ffmpeg").map_err(|e|format!("{stage}: FFmpeg недоступен: {e}"))?.args(args).spawn().map_err(|e|format!("{stage}: не удалось запустить FFmpeg: {e}"))?;
  let spawn_seconds=spawn_mark.elapsed().as_secs_f64();
  let pid=child.pid();let mut child=Some(child);let mut last=base;let mut stderr_tail=String::new();let mut sys=System::new_all();let mut metric_tick=Instant::now();
  let mut startup_seconds:Option<f64>=None;let mut last_progress_at:Option<Instant>=None;let mut last_fps:Option<f64>=None;let mut last_speed:Option<f64>=None;
  loop{
    if crate::license::production_blocked(){if let Some(c)=child.take(){let _=c.kill();}return Err(LICENSE_BLOCKED.into())}
    if cancel.load(Ordering::SeqCst){if let Some(c)=child.take(){let _=c.kill();}return Err(CANCELLED.into())}
    let event=tokio::time::timeout(Duration::from_millis(160),rx.recv()).await;
    if metric_tick.elapsed()>=Duration::from_millis(480){
      let pids=[Pid::from_u32(pid)];sys.refresh_processes(ProcessesToUpdate::Some(&pids),true);sys.refresh_memory();
      if let Some(p)=sys.process(pids[0]){let cpu=(p.cpu_usage()/(sys.cpus().len().max(1) as f32)).clamp(0.0,100.0);emit_progress(app,job,started,timer,last,stage,encoder,attempt,Some((cpu,p.memory(),sys.total_memory(),sys.available_memory())))}
      metric_tick=Instant::now();
    }
    let ev=match event{Err(_)=>continue,Ok(Some(ev))=>ev,Ok(None)=>return Err(format!("{stage}: FFmpeg закрыл канал без статуса завершения"))};
    match ev{
      CommandEvent::Stdout(bytes)|CommandEvent::Stderr(bytes)=>{
        let text=String::from_utf8_lossy(&bytes);stderr_tail.push_str(&text);if stderr_tail.len()>12000{stderr_tail=stderr_tail.split_off(stderr_tail.len()-9000)}
        for line in text.lines(){
          if let Some(raw)=line.strip_prefix("fps=").and_then(|x|x.trim().parse::<f64>().ok()){last_fps=Some(raw);}
          if let Some(raw)=line.strip_prefix("speed=").map(|x|x.trim().trim_end_matches('x')).and_then(|x|x.parse::<f64>().ok()){last_speed=Some(raw);}
          if line.starts_with("progress=")||line.starts_with("out_time_"){if startup_seconds.is_none(){startup_seconds=Some(process_mark.elapsed().as_secs_f64());}last_progress_at=Some(Instant::now());}
          let raw=line.strip_prefix("out_time_us=").or_else(||line.strip_prefix("out_time_ms="));
          if let Some(raw)=raw.and_then(|x|x.parse::<f64>().ok()){
            let out_sec=raw/1_000_000.0;let frac=if expected_sec>0.0{(out_sec/expected_sec).clamp(0.0,1.0)}else{0.0};let p=base+frac*span;
            if p-last>=0.01{last=p;emit_progress(app,job,started,timer,p,stage,encoder,attempt,None)}
          }
        }
      },
      CommandEvent::Error(e)=>return Err(format!("{stage}: {e}")),
      CommandEvent::Terminated(t)=>{
        child.take();
        let process_seconds=process_mark.elapsed().as_secs_f64();let wait_seconds=last_progress_at.map(|x|x.elapsed().as_secs_f64()).unwrap_or(process_seconds);
        diag_line(json!({"kind":"ffmpeg-process","projectId":job.project.id,"launch":launch,"stage":stage,"encoder":encoder,"encoderClass":encoder_class(encoder),"spawnSeconds":spawn_seconds,"startupSeconds":startup_seconds,"processSeconds":process_seconds,"postProgressWaitSeconds":wait_seconds,"encodeFps":last_fps,"realtimeSpeed":last_speed,"expectedSeconds":expected_sec,"args":argv}));
        let key=format!("ffmpeg-{:02}",launch);emit_timing(app,&job.project.id,&key,process_seconds);
        if t.code.unwrap_or(1)!=0{return Err(if stderr_tail.trim().is_empty(){format!("{stage}: FFmpeg завершился с кодом {:?}",t.code)}else{format!("{stage}: {}",stderr_tail.lines().rev().take(12).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\n"))})}
        break
      },
      _=>{}
    }
  }
  emit_progress(app,job,started,timer,base+span,stage,encoder,attempt,None);Ok(())
}

fn base_filter(s:&RenderSettings,label:&str)->String{format!("[{label}]scale={}:{}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={}:{}:(iw-ow)/2:(ih-oh)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,s.fps)}

async fn build_media_clip(app:&AppHandle,job:&QueueJob,media:&str,index:usize,total:usize,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,f64),String>{
  let s=&job.settings;let clip=work.join(format!("source-{index:03}.mp4"));let base=8.0+(index as f64/total.max(1) as f64)*14.0;let span=14.0/total.max(1) as f64;
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();let duration:f64;let graph:String;
  if is_image(media) && total==1{
    duration=encode_static_smart_clip(app,job,media,&clip,started,timer,encoder,attempt,cancel,base,span).await?;
    return Ok((clip,duration));
  }else if is_image(media){
    duration=10.0;args.extend(vec!["-loop","1","-framerate",&s.fps.to_string(),"-i",media].into_iter().map(String::from));graph=format!("{}[outv]",base_filter(s,"0:v"));
  }else{
    let d=probe_duration(app,media).await.unwrap_or(5.0).clamp(1.0,60.0);
    match s.loop_mode.as_str(){
      "crossfade"=>{let cf=s.crossfade_sec.min((d/3.0).max(0.15)).max(0.1);duration=d;args.extend(vec!["-i",media,"-i",media].into_iter().map(String::from));graph=format!("[0:v]trim=duration={d},setpts=PTS-STARTPTS,fps={},settb=AVTB[a];[1:v]trim=duration={d},setpts=PTS-STARTPTS,fps={},settb=AVTB[b];[a][b]xfade=transition=fade:duration={cf}:offset={},trim=start={cf}:duration={d},setpts=PTS-STARTPTS[x];{}[outv]",s.fps,s.fps,(d-cf).max(0.1),base_filter(s,"x"));},
      "pingpong"=>{duration=d*2.0;args.extend(vec!["-i",media].into_iter().map(String::from));graph=format!("[0:v]trim=duration={d},setpts=PTS-STARTPTS,split[f][r];[r]reverse[rr];[f][rr]concat=n=2:v=1:a=0[x];{}[outv]",base_filter(s,"x"));},
      _=>{duration=d;args.extend(vec!["-i",media].into_iter().map(String::from));graph=format!("{}[outv]",base_filter(s,"0:v"));}
    }
  }
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t",&duration.to_string(),"-an"].into_iter().map(String::from));if is_image(media){args.extend(fidelity_video_args(encoder,s));}else{args.extend(encoder_args(encoder,s,false));}args.extend(vec!["-progress","pipe:1","-y",clip.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,&format!("Подготавливаю медиа {}/{}",index+1,total),base,span,duration,encoder,attempt,cancel).await?;Ok((clip,duration))
}

async fn build_lossless_processed_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
  if job.project.audio.is_empty(){return Err("Нет песен".into())}
  let mut durations=Vec::new();let probe_mark=Instant::now();
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
  for a in &job.project.audio{
    durations.push(probe_duration(app,a).await.unwrap_or(180.0).max(0.2));
    args.extend(vec!["-i",a.as_str()].into_iter().map(String::from));
  }
  let ambient_index=job.project.audio.len();let ambient_enabled=job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false);
  if let Some(a)=job.ambient.as_ref().filter(|p|!p.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",a.as_str()].into_iter().map(String::from));}
  emit_timing(app,&job.project.id,"probe",probe_mark.elapsed().as_secs_f64());
  let min_track=durations.iter().copied().fold(f64::INFINITY,f64::min);
  let cf=job.settings.crossfade_sec.clamp(0.0,10.0).min((min_track*0.40).max(0.0));
  let mut graph=String::new();
  for i in 0..job.project.audio.len(){
    if i>0{graph.push(';')}
    graph.push_str(&format!("[{i}:a]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a{i}]"));
  }
  let last=if job.project.audio.len()==1{"a0".to_string()}else if cf>0.01{
    let mut cur="a0".to_string();
    for i in 1..job.project.audio.len(){
      let out=format!("xf{i}");
      graph.push_str(&format!(";[{cur}][a{i}]acrossfade=d={cf}:c1=tri:c2=tri[{out}]"));
      cur=out;
    }
    cur
  }else{
    let inputs=(0..job.project.audio.len()).map(|i|format!("[a{i}]")).collect::<String>();
    graph.push_str(&format!(";{inputs}concat=n={}:v=0:a=1[joined]",job.project.audio.len()));
    "joined".to_string()
  };
  let music="processed_music";
  if job.settings.normalize_lufs{graph.push_str(&format!(";[{last}]loudnorm=I=-14:TP=-1.5:LRA=11[{music}]"));}else{graph.push_str(&format!(";[{last}]anull[{music}]"));}
  if ambient_enabled{
    graph.push_str(&format!(";[{ambient_index}:a]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=0.18[amb];[{music}][amb]amix=inputs=2:duration=first:weights='1 1':normalize=0,alimiter=limit=0.98[outa]"));
  }else{
    graph.push_str(&format!(";[{music}]aresample=48000:async=1:first_pts=0,alimiter=limit=0.98[outa]"));
  }
  let cycle=work.join("audio-crossfade-gapless.m4a");
  let expected=(durations.iter().sum::<f64>()-cf*((durations.len().saturating_sub(1)) as f64)).max(0.2);
  let audio_encoder=choose_audio_encoder(app).await;
  args.extend(vec!["-filter_complex",&graph,"-map","[outa]"].into_iter().map(String::from));
  args.extend(audio_encoder_args(&audio_encoder));
  args.extend(vec!["-movflags","+faststart","-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"Кроссфейд между треками • HQ 320k",35.0,18.0,expected,encoder,attempt,cancel).await?;
  if !probe_audio_decodes(app,&cycle).await{return Err("Crossfade Audio: итоговая дорожка не декодируется".into())}
  let cycle_duration=probe_duration(app,cycle.to_string_lossy().as_ref()).await.unwrap_or(expected);
  Ok((cycle,durations,cycle_duration))
}

async fn materialize_continuous_audio(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,cycle:&Path,final_duration:f64,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<PathBuf,String>{
  let out=work.join("audio-continuous.m4a");
  let args=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-fflags","+genpts","-i",cycle.to_string_lossy().as_ref(),"-t",&final_duration.to_string(),"-map","0:a:0","-c:a","copy","-avoid_negative_ts","make_zero","-movflags","+faststart","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  run_ffmpeg(app,job,started,timer,args,"Фиксирую непрерывную аудиодорожку",53.0,4.0,final_duration,encoder,attempt,cancel).await?;
  if !probe_audio_decodes(app,&out).await{return Err("Crossfade Audio: непрерывная дорожка не декодируется".into())}
  Ok(out)
}

async fn build_source_master(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,f64),String>{
  if smart_repeat_project(job)&&job.project.media.len()==1&&is_image(&job.project.media[0]){let d=hybrid_master_seconds_for_job(app,job).await;emit_timing(app,&job.project.id,"master-loop",0.0);return Ok((PathBuf::from(&job.project.media[0]),d))}
  if fast_multi_still(job){let d=job.project.media.len() as f64*10.0;emit_timing(app,&job.project.id,"master-loop",0.0);return Ok((PathBuf::from(&job.project.media[0]),d))}
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
    let target=((s.width as f64)*e.scale.clamp(0.05,1.5)).round().max(2.0) as u32;let target=if target%2==0{target}else{target+1};
    let scale=if e.fullscreen{format!("scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2:color=black@0",s.width,s.height,s.width,s.height)}else{format!("scale={}:-2:flags=lanczos",target)};
    let x=if e.fullscreen{"0".into()}else{format!("max(0,min(W-w,W*{}-w/2))",e.x.clamp(0.0,1.0))};
    let y=if e.fullscreen{"0".into()}else{format!("max(0,min(H-h,H*{}-h/2))",e.y.clamp(0.0,1.0))};
    if e.mode=="strict-prealpha"{
      graph.push_str(&format!(";[{idx}:v]fps={},setpts=PTS-STARTPTS,format=argb[{fx}];[{base}][{fx}]overlay=x='{x}':y='{y}':shortest=0:repeatlast=1:eof_action=repeat:format=auto[{next}]",s.fps));base=next;continue
    }
    if e.mode=="strict-screen-cache"{
      let px=if e.fullscreen{"0".into()}else{format!("max(0,min(ow-iw,ow*{}-iw/2))",e.x.clamp(0.0,1.0))};let py=if e.fullscreen{"0".into()}else{format!("max(0,min(oh-ih,oh*{}-ih/2))",e.y.clamp(0.0,1.0))};
      graph.push_str(&format!(";[{idx}:v]fps={},format=rgb24,pad={}:{}:'{px}':'{py}':color=black[{fx}];[{base}][{fx}]blend=all_mode=screen:all_opacity=1[{next}]",s.fps,s.width,s.height));base=next;continue
    }
    if e.mode=="screen"||e.mode=="screen-cache"{
      let px=if e.fullscreen{"0".into()}else{format!("max(0,min(ow-iw,ow*{}-iw/2))",e.x.clamp(0.0,1.0))};
      let py=if e.fullscreen{"0".into()}else{format!("max(0,min(oh-ih,oh*{}-ih/2))",e.y.clamp(0.0,1.0))};
      graph.push_str(&format!(";[{idx}:v]fps={},format=rgba,{scale},pad={}:{}:'{px}':'{py}':color=black@0,setsar=1[{fx}];[{base}][{fx}]blend=all_mode=screen:all_opacity=1[{next}]",s.fps,s.width,s.height));
    }else{
      let prep=if e.mode=="prealpha"{format!("[{idx}:v]fps={},format=argb",s.fps)}else if e.mode=="luma"{format!("[{idx}:v]fps={},format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08",s.fps,e.luma_threshold,e.luma_tolerance)}else{format!("[{idx}:v]fps={},format=rgba,colorkey={}:{}:{}",s.fps,color_ffmpeg(&e.key_color),e.similarity.clamp(0.001,0.60),e.blend.clamp(0.001,0.35))};
      graph.push_str(&format!(";{prep},{scale}[{fx}];[{base}][{fx}]overlay=x='{x}':y='{y}':shortest=1:eof_action=repeat:format=auto[{next}]"));
    }
    base=next;
  }
  (graph,base)
}

async fn prepare_overlays(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,encoder:&str,attempt:u32)->Result<(Vec<EffectPreset>,Vec<SubscribePreset>),String>{
  if smart_repeat_project(job){
    emit_progress(app,job,started,timer,26.0,"Strict 8.56: проверяю быстрый lossless Effects cache",encoder,attempt,None);let mark=Instant::now();let mut fx=Vec::new();
    for e in job.effects.iter().filter(|e|e.enabled){match cache::prepare_strict_856(app,e,30,1920,1080).await{Ok(p)=>fx.push(p),Err(err)=>return Err(format!("Strict 8.56 Effects cache: {err}"))}}
    let effects_sec=mark.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"effects-cache",effects_sec);emit_timing(app,&job.project.id,"effects",effects_sec);emit_timing(app,&job.project.id,"subscribe",0.0);emit_progress(app,job,started,timer,31.0,"Strict 8.56: lossless Effects cache готов",encoder,attempt,None);return Ok((fx,job.subscribes.clone()))
  }
  emit_progress(app,job,started,timer,26.0,"Проверяю кэш Effects и Subscribe",encoder,attempt,None);let mark=Instant::now();let effects_mark=Instant::now();let mut fx=Vec::new();let mut subs=Vec::new();
  for e in &job.effects{
    if !e.enabled{continue}
    match cache::prepare(app,e,job.settings.fps).await{Ok(p)=>fx.push(p),Err(err)=>emit_warning(app,&job.project.id,&format!("Effect '{}' пропущен: {}",e.name,err))}
  }
  emit_timing(app,&job.project.id,"effects",effects_mark.elapsed().as_secs_f64());let subscribe_mark=Instant::now();
  for s in &job.subscribes{
    if !s.effect.enabled{continue}
    match cache::prepare(app,&s.effect,job.settings.fps).await{Ok(effect)=>{let mut p=s.clone();p.effect=effect;subs.push(p)},Err(err)=>emit_warning(app,&job.project.id,&format!("Subscribe '{}' пропущен: {}",s.effect.name,err))}
  }
  emit_timing(app,&job.project.id,"subscribe",subscribe_mark.elapsed().as_secs_f64());emit_timing(app,&job.project.id,"effects-cache",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,31.0,"Кэш Effects и Subscribe готов",encoder,attempt,None);Ok((fx,subs))
}

fn active_effects_at(effects:&[EffectPreset],t:f64,final_duration:f64)->Vec<EffectPreset>{
  effects.iter().filter(|e|e.enabled&&e.start_sec<=t&&e.end_sec.unwrap_or(final_duration)>t).cloned().collect()
}
fn state_key(effects:&[EffectPreset])->String{let mut ids=effects.iter().map(|e|e.id.clone()).collect::<Vec<_>>();ids.sort();ids.join("|")}

async fn build_variant(app:&AppHandle,job:&QueueJob,source_master:&Path,master_duration:f64,effects:&[EffectPreset],work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,variant_no:usize,started:i64,timer:&Instant)->Result<PathBuf,String>{
  let smart=smart_repeat_project(job)&&job.project.media.len()==1&&is_image(&job.project.media[0]);
  if effects.is_empty()&&!smart{return Ok(source_master.to_path_buf())}
  let out=work.join(format!("variant-{variant_no:03}.mp4"));let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();let input_start;
  let base_graph:String;
  if smart{
    args.extend(vec!["-loop","1","-framerate",&job.settings.fps.to_string(),"-i",job.project.media[0].as_str()].into_iter().map(String::from));input_start=1;base_graph=format!("{}[b0]",base_filter(&job.settings,"0:v"));
  }else{
    args.extend(vec!["-stream_loop","-1","-i",source_master.to_string_lossy().as_ref()].into_iter().map(String::from));input_start=1;base_graph="[0:v]setpts=PTS-STARTPTS[b0]".into();
  }
  for e in effects{args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}
  let (graph,last)=apply_effects_filter(base_graph,"b0".into(),effects,&job.settings,input_start);let graph=format!("{graph};[{last}]format=yuv420p[outv]");
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t",&master_duration.to_string(),"-an"].into_iter().map(String::from));
  if smart{args.extend(hybrid_fidelity_args(&job.settings,encoder,master_duration));}else{args.extend(encoder_args(encoder,&job.settings,false));}
  args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"Hybrid Fidelity: собираю короткий master",32.0,3.0,master_duration,encoder,attempt,cancel).await?;Ok(out)
}

async fn build_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
  let mark=Instant::now();let mut durations=Vec::new();for a in &job.project.audio{durations.push(probe_duration(app,a).await.unwrap_or(180.0).max(0.2));}
  if job.project.audio.is_empty(){return Err("Нет песен".into())}
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();for a in &job.project.audio{args.extend(vec!["-i",a.as_str()].into_iter().map(String::from));}
  let ambient_index=job.project.audio.len();if let Some(a)=job.ambient.as_ref().filter(|p|!p.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",a.as_str()].into_iter().map(String::from));}
  let mut labels=Vec::new();let mut graph=String::new();for i in 0..job.project.audio.len(){if i>0{graph.push(';')}graph.push_str(&format!("[{i}:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a{i}]"));labels.push(format!("a{i}"));}
  let min_duration=durations.iter().copied().fold(f64::INFINITY,f64::min);let cf=job.settings.crossfade_sec.clamp(0.0,10.0).min((min_duration/3.0).max(0.05));let mut last=labels[0].clone();for i in 1..labels.len(){let out=format!("x{i}");graph.push_str(&format!(";[{last}][{}]acrossfade=d={}:c1=tri:c2=tri[{out}]",labels[i],cf));last=out;}
  let music="music";if job.settings.normalize_lufs{graph.push_str(&format!(";[{last}]loudnorm=I=-14:TP=-1.5:LRA=11[{music}]"));}else{graph.push_str(&format!(";[{last}]anull[{music}]"));}
  if job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false){graph.push_str(&format!(";[{ambient_index}:a]aresample=48000,volume=0.18[amb];[{music}][amb]amix=inputs=2:duration=first:weights='1 1':normalize=0,alimiter=limit=0.97[outa]"));}else{graph.push_str(&format!(";[{music}]alimiter=limit=0.97[outa]"));}
  let audio_encoder=choose_audio_encoder(app).await;let cycle=work.join("audio-cycle.m4a");args.extend(vec!["-filter_complex",&graph,"-map","[outa]"].into_iter().map(String::from));args.extend(audio_encoder_args(&audio_encoder));args.extend(vec!["-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from));
  let expected=(durations.iter().sum::<f64>()-cf*((durations.len().saturating_sub(1)) as f64)).max(1.0);run_ffmpeg(app,job,started,timer,args,"Подготавливаю музыку",35.0,20.0,expected,encoder,attempt,cancel).await?;
  let cycle_duration=probe_duration(app,cycle.to_string_lossy().as_ref()).await.unwrap_or(expected);emit_timing(app,&job.project.id,"audio",mark.elapsed().as_secs_f64());Ok((cycle,durations,cycle_duration))
}

async fn smart_repeat_visual_seconds(app:&AppHandle,base:f64,effects:&[EffectPreset])->f64{
  let mut seconds=base.max(1.0);
  for e in effects.iter().filter(|e|e.enabled&&!e.source.trim().is_empty()){
    if let Ok(d)=probe_duration(app,&e.source).await{seconds=seconds.max(d.clamp(1.0,60.0));}
  }
  seconds
}

fn smart_final_duration(target:f64,durations:&[f64],crossfade:f64,mode:&str)->f64{if mode!="whole-track"||durations.is_empty(){return target}let mut t=0.0;let mut i=0usize;while t<target{let add=(durations[i%durations.len()]-if t>0.0{crossfade}else{0.0}).max(0.1);t+=add;i+=1;}t}

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
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t",&len.to_string(),"-an"].into_iter().map(String::from));if smart_repeat_project(job){args.extend(hybrid_fidelity_args(&job.settings,encoder,len));}else{args.extend(encoder_args(encoder,&job.settings,false));}args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));run_ffmpeg(app,job,started,timer,args,"Добавляю Subscribe",base,span,len,encoder,attempt,cancel).await
}

async fn assemble_visual(app:&AppHandle,job:&QueueJob,source_master:&Path,master_duration:f64,effects:&[EffectPreset],subs:&[SubscribePreset],final_duration:f64,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<VisualSource,String>{
  let mark=Instant::now();let events=subscribe_events(app,subs,final_duration).await;let has_timed=timed_effects(effects,final_duration);
  let mut variants:HashMap<String,(PathBuf,f64)>=HashMap::new();
  let initial=active_effects_at(effects,0.001,final_duration);let key=state_key(&initial);let p=build_variant(app,job,source_master,master_duration,&initial,work,encoder,attempt,cancel,0,started,timer).await?;variants.insert(key.clone(),(p,master_duration));
  if events.is_empty()&&!has_timed{emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());return Ok(VisualSource::Loop(variants.get(&key).unwrap().0.clone()))}
  let mut boundaries=vec![0.0,final_duration];for e in effects.iter().filter(|e|e.enabled){if e.start_sec>0.0&&e.start_sec<final_duration{boundaries.push(e.start_sec)}if let Some(x)=e.end_sec{if x>0.0&&x<final_duration{boundaries.push(x)}}}for e in &events{boundaries.push(e.start);boundaries.push(e.end)}
  boundaries.sort_by(|a,b|a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));boundaries.dedup_by(|a,b|(*a-*b).abs()<0.001);
  let intervals=boundaries.windows(2).filter(|w|w[1]-w[0]>0.005).map(|w|(w[0],w[1])).collect::<Vec<_>>();let mut segments=Vec::new();let mut sub_cache:HashMap<String,PathBuf>=HashMap::new();
  for (i,(a,b)) in intervals.iter().copied().enumerate(){if cancel.load(Ordering::SeqCst){return Err(CANCELLED.into())}let mid=(a+b)/2.0;let active_fx=active_effects_at(effects,mid,final_duration);let k=state_key(&active_fx);
    if !variants.contains_key(&k){let no=variants.len();let v=build_variant(app,job,source_master,master_duration,&active_fx,work,encoder,attempt,cancel,no,started,timer).await?;variants.insert(k.clone(),(v,master_duration));}
    let (variant,vd)=variants.get(&k).cloned().unwrap();let active_sub=events.iter().filter(|e|e.start<=mid&&e.end>mid).cloned().collect::<Vec<_>>();let seg=work.join(format!("visual-seg-{i:04}.mp4"));let base=64.0+(i as f64/intervals.len().max(1) as f64)*22.0;let span=22.0/intervals.len().max(1) as f64;
    if active_sub.is_empty(){
      copy_segment(app,job,&variant,vd,a,b-a,&seg,encoder,attempt,cancel,base,span,started,timer).await?;segments.push(seg);
    }else{
      let phase=(a%vd.max(0.1)).max(0.0);let mut ids=active_sub.iter().map(|e|e.sub.effect.id.clone()).collect::<Vec<_>>();ids.sort();
      let ck=format!("{}|{:.3}|{:.3}|{}",k,phase,b-a,ids.join(","));
      if let Some(existing)=sub_cache.get(&ck){segments.push(existing.clone());}
      else{render_sub_segment(app,job,&variant,vd,a,b-a,&active_sub,&seg,encoder,attempt,cancel,base,span,started,timer).await?;sub_cache.insert(ck,seg.clone());segments.push(seg);}
    }
  }
  let list=work.join("visual-concat.txt");let text=segments.iter().map(|p|format!("file '{}'",p.to_string_lossy().replace('\\',"/"))).collect::<Vec<_>>().join("\n");std::fs::write(&list,text).map_err(|e|e.to_string())?;
  if smart_repeat_project(job){emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());return Ok(VisualSource::Concat(list))}
  let long=work.join("video-long.mp4");let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-an","-c:v","copy","-progress","pipe:1","-y",long.to_string_lossy().as_ref()].into_iter().map(String::from).collect();run_ffmpeg(app,job,started,timer,args,"Склеиваю визуальную дорожку",86.0,4.0,final_duration,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());Ok(VisualSource::Long(long))
}

fn write_side_files(job:&QueueJob,output_dir:&Path,durations:&[f64],final_duration:f64,result_stem:&str)->Result<(),String>{
  let name=safe_name(result_stem);let time_dir=output_dir.join("timecodes");let log_dir=output_dir.join("logs");std::fs::create_dir_all(&time_dir).map_err(|e|e.to_string())?;std::fs::create_dir_all(&log_dir).map_err(|e|e.to_string())?;
  let mut t=0.0;let mut i=0usize;let cf=job.settings.crossfade_sec.max(0.0);let mut tc=String::new();while t<final_duration-0.1{let path=&job.project.audio[i%job.project.audio.len()];let title=Path::new(path).file_stem().and_then(|x|x.to_str()).unwrap_or("Track");tc.push_str(&format!("{} {}\n",fmt_ts(t),title));let d=durations[i%durations.len()];t+=(d-if i>0{cf}else{0.0}).max(0.1);i+=1;if i>10000{break}}
  std::fs::write(time_dir.join(format!("{} — timecodes.txt",name)),tc).map_err(|e|e.to_string())?;let tracklist=job.project.audio.iter().enumerate().map(|(i,p)|format!("{}. {}",i+1,Path::new(p).file_name().and_then(|x|x.to_str()).unwrap_or(p))).collect::<Vec<_>>().join("\n");std::fs::write(output_dir.join(format!("{} — tracklist.txt",name)),tracklist).map_err(|e|e.to_string())?;std::fs::write(log_dir.join(format!("{} — project.json",name)),serde_json::to_vec_pretty(job).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;Ok(())
}

async fn verify_result(app:&AppHandle,out:&Path,expected:f64,s:&RenderSettings)->Result<(),String>{
  let d=probe_duration(app,out.to_string_lossy().as_ref()).await?;
  if (d-expected).abs()>4.0{return Err(format!("Финальный файл имеет неверную длительность: {:0.1} сек вместо {:0.1}",d,expected))}
  if !probe_has_audio(app,out).await{return Err("В финальном файле отсутствует аудиодорожка".into())}
  if !probe_audio_decodes(app,out).await{return Err("Аудиодорожка есть, но не воспроизводится/не декодируется".into())}
  let args=vec!["-v","error","-select_streams","v:0","-show_entries","stream=width,height,avg_frame_rate","-of","json",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  let (stdout,_)=output(app,"ffprobe",args).await?;
  let v:serde_json::Value=serde_json::from_slice(&stdout).map_err(|e|e.to_string())?;
  let stream=v.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()).ok_or("FFprobe не вернул видеопоток")?;
  let w=stream.get("width").and_then(|x|x.as_u64()).unwrap_or(0) as u32;
  let h=stream.get("height").and_then(|x|x.as_u64()).unwrap_or(0) as u32;
  if w!=s.width||h!=s.height{return Err(format!("Неверное разрешение результата: {}x{} вместо {}x{}",w,h,s.width,s.height))}
  let rate=stream.get("avg_frame_rate").and_then(|x|x.as_str()).unwrap_or("0/1");
  let mut it=rate.split('/');let n=it.next().and_then(|x|x.parse::<f64>().ok()).unwrap_or(0.0);let den=it.next().and_then(|x|x.parse::<f64>().ok()).unwrap_or(1.0).max(0.0001);let fps=n/den;
  if s.fps==60&&(fps<59.0||fps>61.0){return Err(format!("Финальный файл не 60 FPS: {:.3}",fps))}
  Ok(())
}


async fn verify_strict_857_result(app:&AppHandle,out:&Path,expected:f64,original_audio:bool,track_durations:&[f64])->Result<(),String>{
  let bytes=std::fs::metadata(out).map_err(|e|format!("Strict 8.64 final stat: {e}"))?.len();
  if bytes<1_000_000{return Err(format!("Strict 8.64 final file too small: {} bytes",bytes))}
  let d=probe_duration(app,out.to_string_lossy().as_ref()).await?;
  if (d-expected).abs()>1.0{return Err(format!("Strict 8.57 final duration: {:.3} вместо {:.3}",d,expected))}
  let args=vec!["-v","error","-show_entries","stream=codec_type,codec_name,pix_fmt,width,height,avg_frame_rate,sample_rate,channels","-of","json",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  let (stdout,_)=output(app,"ffprobe",args).await?;let v:serde_json::Value=serde_json::from_slice(&stdout).map_err(|e|e.to_string())?;let streams=v.get("streams").and_then(|x|x.as_array()).ok_or("Strict 8.57: FFprobe streams отсутствуют")?;
  let video=streams.iter().find(|x|x.get("codec_type").and_then(|y|y.as_str())==Some("video")).ok_or("Strict 8.57: video stream отсутствует")?;
  let audio=streams.iter().find(|x|x.get("codec_type").and_then(|y|y.as_str())==Some("audio")).ok_or("Strict 8.57: audio stream отсутствует")?;
  if video.get("codec_name").and_then(|x|x.as_str())!=Some("hevc"){return Err("Strict 8.57: final video codec не HEVC".into())}
  if video.get("pix_fmt").and_then(|x|x.as_str())!=Some("yuv420p"){return Err("Strict 8.57: final pixel format не yuv420p".into())}
  if video.get("width").and_then(|x|x.as_u64())!=Some(1920)||video.get("height").and_then(|x|x.as_u64())!=Some(1080){return Err("Strict 8.57: final resolution не 1920x1080".into())}
  if video.get("avg_frame_rate").and_then(|x|x.as_str())!=Some("60/1"){return Err(format!("Strict 8.57: final FPS {:?}, ожидается 60/1",video.get("avg_frame_rate")))}
  let audio_codec=audio.get("codec_name").and_then(|x|x.as_str()).unwrap_or("");
  if original_audio&&audio_codec!="mp3"{return Err(format!("Strict 8.63: final audio codec {:?}, ожидается untouched MP3",audio.get("codec_name")))}
  if !original_audio&&audio_codec!="aac"{return Err(format!("Strict 8.63 Processed Audio: final audio codec {:?}, ожидается AAC",audio.get("codec_name")))}
  for pos in [0.0,(expected*0.5).max(0.0),(expected-2.0).max(0.0)]{
    let ss=format!("{pos:.3}");let args=vec!["-v","error","-ss",ss.as_str(),"-i",out.to_string_lossy().as_ref(),"-map","0:v:0","-frames:v","2","-f","null","-"].into_iter().map(String::from).collect();
    output(app,"ffmpeg",args).await.map_err(|e|format!("Strict 8.57 video seek/decode @ {ss}s: {e}"))?;
  }
  let mut audio_positions=vec![0.0,(expected*0.5).max(0.0),(expected-10.0).max(0.0),(expected-2.0).max(0.0)];
  if original_audio&&track_durations.len()>1{
    let boundary=track_durations[0].max(0.2);
    audio_positions.push((boundary-0.20).max(0.0));
    audio_positions.push((boundary+0.20).min((expected-0.1).max(0.0)));
  }
  audio_positions.sort_by(|a,b|a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
  audio_positions.dedup_by(|a,b|(*a-*b).abs()<0.05);
  for pos in audio_positions{
    let ss=format!("{pos:.3}");let args=vec!["-v","error","-ss",ss.as_str(),"-i",out.to_string_lossy().as_ref(),"-map","0:a:0","-t","0.25","-f","null","-"].into_iter().map(String::from).collect();
    output(app,"ffmpeg",args).await.map_err(|e|format!("Strict 8.64 audio seek/decode @ {ss}s: {e}"))?;
  }
  Ok(())
}


#[derive(Clone)]
struct Periodic852Plan{first_frames:usize,anchor_frames:usize,repeat_frames:usize,master_frames:usize,sub:SubscribePreset}

fn periodic_852_plan(job:&QueueJob,effects:&[EffectPreset],subs:&[SubscribePreset],final_duration:f64)->Option<Periodic852Plan>{
  if !smart_repeat_project(job)||timed_effects(effects,final_duration){return None}
  let active=subs.iter().filter(|x|x.effect.enabled&&!x.effect.source.trim().is_empty()).collect::<Vec<_>>();
  if active.len()!=1{return None}
  let sub=active[0];if sub.effect.mode=="screen"||sub.effect.mode=="screen-cache"||sub.repeat_every_sec<60.0{return None}
  let fps=job.settings.fps.max(1) as f64;let first=sub.first_at_sec.min(sub.second_at_sec).max(0.0);let anchor=sub.first_at_sec.max(sub.second_at_sec).max(0.0);
  let first_frames=(first*fps).round() as usize;let anchor_frames=(anchor*fps).round() as usize;let repeat_frames=(sub.repeat_every_sec*fps).round() as usize;
  if repeat_frames==0||anchor_frames==0{return None}
  let desired=(30.0*fps).round() as usize;let lo=(20.0*fps).round() as usize;let hi=(40.0*fps).round() as usize;
  let mut best=None::<usize>;let mut best_dist=usize::MAX;
  for d in lo.max(1)..=hi.max(lo.max(1)){if repeat_frames%d==0{let dist=d.abs_diff(desired);if dist<best_dist{best=Some(d);best_dist=dist}}}
  let master_frames=best?;
  // The common ENDLUME schedule (10s/20s/300s) stays inside the first master.
  // More exotic schedules keep the proven 8.51 planner instead of being guessed at.
  if anchor_frames>=master_frames||first_frames>anchor_frames{return None}
  Some(Periodic852Plan{first_frames,anchor_frames,repeat_frames,master_frames,sub:sub.clone()})
}

async fn probe_video_frames_852(app:&AppHandle,path:&Path)->Result<usize,String>{
  let args=vec!["-v","error","-count_frames","-select_streams","v:0","-show_entries","stream=nb_read_frames","-of","default=nw=1:nk=1",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  let (o,_)=output(app,"ffprobe",args).await?;String::from_utf8_lossy(&o).trim().parse::<usize>().map_err(|_|format!("Не удалось посчитать кадры: {}",path.display()))
}

async fn probe_video_packets_857(app:&AppHandle,path:&Path)->Result<usize,String>{
  let args=vec!["-v","error","-count_packets","-select_streams","v:0","-show_entries","stream=nb_read_packets","-of","default=nw=1:nk=1",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  let (o,_)=output(app,"ffprobe",args).await?;String::from_utf8_lossy(&o).trim().parse::<usize>().map_err(|_|format!("Не удалось посчитать video packets: {}",path.display()))
}

async fn build_periodic_master_852(app:&AppHandle,job:&QueueJob,effects:&[EffectPreset],plan:&Periodic852Plan,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<PathBuf,String>{
  let out=work.join("periodic-852-master.mp4");let fps=job.settings.fps.max(1);let work_fps=if fps>=50{30}else{fps};let duration=plan.master_frames as f64/fps as f64;
  let mut ws=job.settings.clone();ws.fps=work_fps;
  let base_still=work.join("periodic-860-base.png");
  if !base_still.is_file(){
    let vf=base_filter(&ws,"0:v");let vf=vf.trim_start_matches("[0:v]").to_string();
    let prep=vec!["-hide_banner","-loglevel","error","-i",job.project.media[0].as_str(),"-vf",vf.as_str(),"-frames:v","1","-compression_level","1","-y",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
    output(app,"ffmpeg",prep).await.map_err(|e|format!("8.60 periodic static base preprocess: {e}"))?;
  }
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",&work_fps.to_string(),"-i",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}
  let base=format!("[0:v]fps={work_fps},setsar=1[b0]");let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps={fps},format=yuv420p[outv]");
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-frames:v",&plan.master_frames.to_string(),"-an"].into_iter().map(String::from));args.extend(periodic_fidelity_args(&job.settings,encoder,duration));args.extend(vec!["-fps_mode","cfr","-r",&fps.to_string(),"-video_track_timescale","60000","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"8.52: собираю 30-секундный fidelity master",58.0,10.0,duration,encoder,attempt,cancel).await?;
  let packets=probe_video_packets_857(app,&out).await?;if packets!=plan.master_frames{return Err(format!("Strict 8.67 periodic master packet integrity: packets={packets}/{}",plan.master_frames))}Ok(out)
}

async fn copy_head_frames_852(app:&AppHandle,job:&QueueJob,src:&Path,frames:usize,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<(),String>{
  if frames==0{return Err("8.52: zero-frame head requested".into())}
  let args=vec!["-hide_banner","-loglevel","error","-i",src.to_string_lossy().as_ref(),"-map","0:v:0","-frames:v",&frames.to_string(),"-an","-c:v","copy","-avoid_negative_ts","make_zero","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  run_ffmpeg(app,job,started,timer,args,"8.52: готовлю zero-copy video slice",68.0,1.0,frames as f64/job.settings.fps.max(1) as f64,encoder,attempt,cancel).await?;let packets=probe_video_packets_857(app,out).await?;if packets!=frames{return Err(format!("Strict 8.67 slice packet integrity: packets={packets}/{frames}"))}Ok(())
}

async fn render_periodic_sub_852(app:&AppHandle,job:&QueueJob,master:&Path,sub:&SubscribePreset,start_frame:usize,frames:usize,work:&Path,label:&str,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<PathBuf,String>{
  let fps=job.settings.fps.max(1);let work_fps=if fps>=50{30}else{fps};let phase=start_frame as f64/fps as f64;let out=work.join(format!("periodic-852-sub-{label}.mp4"));let mut ws=job.settings.clone();ws.fps=work_fps;
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&phase.to_string(),"-i",master.to_string_lossy().as_ref(),"-i",sub.effect.source.as_str()].into_iter().map(String::from).collect();
  let one=vec![sub.effect.clone()];let (graph,last)=apply_effects_filter(format!("[0:v]fps={work_fps},setpts=PTS-STARTPTS[b0]"),"b0".into(),&one,&ws,1);let graph=graph.replace(":shortest=1:eof_action=repeat",":shortest=0:eof_action=pass");let graph=format!("{graph};[{last}]fps={fps},format=yuv420p[outv]");
  let duration=frames as f64/fps as f64;args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-frames:v",&frames.to_string(),"-an"].into_iter().map(String::from));args.extend(periodic_fidelity_args(&job.settings,encoder,duration));args.extend(vec!["-fps_mode","cfr","-r",&fps.to_string(),"-video_track_timescale","60000","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"8.57: добавляю Subscribe один раз на цикл",69.0,4.0,duration,encoder,attempt,cancel).await?;let packets=probe_video_packets_857(app,&out).await?;if packets!=frames{return Err(format!("Strict 8.67 Subscribe packet integrity: packets={packets}/{frames}"))}Ok(out)
}

async fn concat_video_parts_852(app:&AppHandle,job:&QueueJob,parts:&[PathBuf],out:&Path,expected_frames:usize,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<(),String>{
  let list=work.join("periodic-852-video-list.txt");let body=parts.iter().map(|x|format!("file '{}'
",ffconcat_escape(x))).collect::<String>();std::fs::write(&list,body).map_err(|e|e.to_string())?;
  let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-map","0:v:0","-an","-c:v","copy","-avoid_negative_ts","make_zero","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();run_ffmpeg(app,job,started,timer,args,"8.57: собираю один физический video-cycle",74.0,3.0,expected_frames as f64/job.settings.fps.max(1) as f64,encoder,attempt,cancel).await?;let packets=probe_video_packets_857(app,out).await?;if packets!=expected_frames{return Err(format!("Strict 8.67 seed packet integrity: packets={packets}/{expected_frames}"))}Ok(())
}


fn strict_856_validate_natural_size(path:&Path)->Result<(),String>{
  let current=std::fs::metadata(path).map_err(|e|format!("8.64 size sanity gate: {e}"))?.len();
  // 8.64: file-size ranges are targets, never a reason to damage or reject original audio.
  // Only reject an obviously broken/truncated result here; no artificial upper cap.
  if current<1_000_000{return Err(format!("Strict 8.64: итоговый файл подозрительно мал: {} bytes",current))}
  Ok(())
}

async fn render_multi_still_zero_copy_863(app:&AppHandle,job:&QueueJob,audio:&AudioSource,final_duration:f64,work:&Path,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<bool,String>{
  if !fast_multi_still(job){return Ok(false)}
  if !strict_856_encoder_allowed(encoder){return Err(format!("Strict 8.63: HEVC encoder {encoder} не разрешён fast multi-still pipeline"))}
  const PHYSICAL_FRAMES_PER_STILL:usize=30;
  const LOGICAL_FRAMES_PER_STILL:usize=600;
  let fps=60usize;let physical_seconds=PHYSICAL_FRAMES_PER_STILL as f64/fps as f64;
  let mut clips=Vec::with_capacity(job.project.media.len());let prep_mark=Instant::now();
  for (i,media) in job.project.media.iter().enumerate(){
    if cancel.load(Ordering::SeqCst){return Err(CANCELLED.into())}
    let clip=work.join(format!("fast-863-still-{i:03}.mp4"));
    let graph=format!("{}[outv]",base_filter(&job.settings,"0:v"));
    let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate","60","-i",media.as_str(),"-filter_complex",&graph,"-map","[outv]","-frames:v",&PHYSICAL_FRAMES_PER_STILL.to_string(),"-an"].into_iter().map(String::from).collect();
    args.extend(hybrid_fidelity_args(&job.settings,encoder,physical_seconds));
    args.extend(vec!["-fps_mode","cfr","-r","60","-video_track_timescale","60000","-progress","pipe:1","-y",clip.to_string_lossy().as_ref()].into_iter().map(String::from));
    let base=8.0+(i as f64/job.project.media.len().max(1) as f64)*14.0;let span=14.0/job.project.media.len().max(1) as f64;
    run_ffmpeg(app,job,started,timer,args,&format!("Fast multi-still {}/{}",i+1,job.project.media.len()),base,span,physical_seconds,encoder,attempt,cancel).await?;
    let frames=probe_video_frames_852(app,&clip).await?;if frames!=PHYSICAL_FRAMES_PER_STILL{return Err(format!("8.63 multi-still physical master frames={frames}, expected {PHYSICAL_FRAMES_PER_STILL}"))}
    clips.push(clip);
  }
  emit_timing(app,&job.project.id,"image-preprocess",prep_mark.elapsed().as_secs_f64());

  let physical=if clips.len()==1{
    emit_timing(app,&job.project.id,"visual-master",0.0);
    clips[0].clone()
  }else{
    let list=work.join("fast-865-physical-list.txt");let body=clips.iter().map(|p|format!("file '{}'",p.to_string_lossy().replace('\\',"/"))).collect::<Vec<_>>().join("\n");std::fs::write(&list,body).map_err(|e|e.to_string())?;
    let physical=work.join("fast-865-physical-pool.mp4");let concat_mark=Instant::now();
    let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-an","-c:v","copy","-progress","pipe:1","-y",physical.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
    run_ffmpeg(app,job,started,timer,args,"Fast still physical cycle",24.0,4.0,physical_seconds*job.project.media.len() as f64,encoder,attempt,cancel).await?;
    emit_timing(app,&job.project.id,"visual-master",concat_mark.elapsed().as_secs_f64());
    physical
  };
  let pool_frames=probe_video_frames_852(app,&physical).await?;let expected_pool=PHYSICAL_FRAMES_PER_STILL*job.project.media.len();if pool_frames!=expected_pool{return Err(format!("8.65 still pool frames={pool_frames}, expected {expected_pool}"))}

  let seed=work.join("fast-865-still-seed.mp4");let mut mux:Vec<String>=vec!["-hide_banner","-loglevel","error","-i",physical.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  match audio{AudioSource::Loop(p)=>mux.extend(vec!["-stream_loop","-1","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::Long(p)=>mux.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::ConcatList(p)=>mux.extend(vec!["-stream_loop","-1","-f","concat","-safe","0","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}
  mux.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-progress","pipe:1","-y",seed.to_string_lossy().as_ref()].into_iter().map(String::from));
  let audio_stage=if matches!(audio,&AudioSource::Loop(_)|&AudioSource::ConcatList(_)){"Fast Original Audio • MP3 packet-copy"}else{"Processed Audio • AAC packet-copy into final container"};
  let mux_mark=Instant::now();run_ffmpeg(app,job,started,timer,mux,audio_stage,60.0,18.0,final_duration,encoder,attempt,cancel).await?;let mux_seconds=mux_mark.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"audio-mux",mux_seconds);if let Ok(meta)=std::fs::metadata(&seed){let mb_s=(meta.len() as f64/1_048_576.0)/mux_seconds.max(0.001);let _=app.emit("engine-profile",json!({"id":job.project.id,"diskWriteMBs":mb_s}));}

  let mut cycle=Vec::with_capacity(LOGICAL_FRAMES_PER_STILL*job.project.media.len());
  for image in 0..job.project.media.len(){let start=image*PHYSICAL_FRAMES_PER_STILL;for i in 0..LOGICAL_FRAMES_PER_STILL{cycle.push(start+(i%PHYSICAL_FRAMES_PER_STILL));}}
  let total_frames=(final_duration*fps as f64).round().max(cycle.len() as f64) as usize;let _=app.emit("engine-profile",json!({"id":job.project.id,"physicalEncodedFrames":pool_frames,"logicalFrames":total_frames,"manifestFrames":total_frames}));let selected=(0..total_frames).map(|i|cycle[i%cycle.len()]).collect::<Vec<_>>();
  let manifest_mark=Instant::now();ensure_license_allowed()?;crate::mp4_manifest::remap_video_samples(&seed,&seed,&selected)?;ensure_license_allowed()?;emit_timing(app,&job.project.id,"manifest-expand",manifest_mark.elapsed().as_secs_f64());

  let finalize_mark=Instant::now();finalize_local_output(&seed,out).map_err(|e|format!("8.65 still MP4 finalize: {e}"))?;strict_856_validate_natural_size(out)?;ensure_license_allowed()?;emit_timing(app,&job.project.id,"finalize",finalize_mark.elapsed().as_secs_f64());
  emit_progress(app,job,started,timer,96.0,"FAST_ONE_IMAGE / MULTI_STILL zero-copy готов",encoder,attempt,None);Ok(true)
}

async fn render_zero_sub_zero_copy_856(app:&AppHandle,job:&QueueJob,effects:&[EffectPreset],subs:&[SubscribePreset],audio:&AudioSource,master_duration:f64,final_duration:f64,work:&Path,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<bool,String>{
  if !smart_repeat_project(job)||timed_effects(effects,final_duration){return Ok(false)}if subs.iter().any(|x|x.effect.enabled&&!x.effect.source.trim().is_empty()){return Ok(false)}if !strict_856_encoder_allowed(encoder){return Err(format!("Strict 8.62: HEVC encoder {encoder} не разрешён strict pipeline"))}
  let fps=60u32;let work_fps=30u32;let duration=master_duration.clamp(12.0,60.0);let master_frames=(duration*fps as f64).round() as usize;let mut ws=job.settings.clone();ws.fps=work_fps;
  let base_still=work.join("strict-860-base.png");let image_prep_mark=Instant::now();
  if !base_still.is_file(){
    let vf=base_filter(&ws,"0:v");
    let vf=vf.trim_start_matches("[0:v]").to_string();
    let prep=vec!["-hide_banner","-loglevel","error","-i",job.project.media[0].as_str(),"-vf",vf.as_str(),"-frames:v","1","-compression_level","1","-y",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
    output(app,"ffmpeg",prep).await.map_err(|e|format!("Strict 8.60 static base preprocess: {e}"))?;
  }
  emit_timing(app,&job.project.id,"image-preprocess",image_prep_mark.elapsed().as_secs_f64());
  let master=work.join("strict-856-master.mp4");let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-filter_complex_threads","8","-loop","1","-framerate","30","-i",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}
  let base="[0:v]fps=30,setsar=1[b0]".to_string();let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps=60,format=yuv420p[outv]");args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-frames:v",&master_frames.to_string(),"-an"].into_iter().map(String::from));args.extend(hybrid_fidelity_args(&job.settings,encoder,duration));args.extend(vec!["-fps_mode","cfr","-r","60","-video_track_timescale","60000","-progress","pipe:1","-y",master.to_string_lossy().as_ref()].into_iter().map(String::from));
  let vm=Instant::now();run_ffmpeg(app,job,started,timer,args,"Strict 8.57: fidelity master полного Effects-цикла",55.0,18.0,duration,encoder,attempt,cancel).await?;let visual_master_seconds=vm.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"strict-visual-master",visual_master_seconds);emit_timing(app,&job.project.id,"visual-master",visual_master_seconds);let got=probe_video_frames_852(app,&master).await?;let packets=probe_video_packets_857(app,&master).await?;if got!=master_frames||packets!=master_frames{return Err(format!("Strict 8.57 master integrity: frames={got}/{master_frames}, packets={packets}/{master_frames}"))}
  let seed=work.join("strict-856-seed.mp4");let mut mux:Vec<String>=vec!["-hide_banner","-loglevel","error","-i",master.to_string_lossy().as_ref()].into_iter().map(String::from).collect();match audio{AudioSource::Loop(p)=>mux.extend(vec!["-stream_loop","-1","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::Long(p)=>mux.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::ConcatList(p)=>mux.extend(vec!["-stream_loop","-1","-f","concat","-safe","0","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))};mux.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-progress","pipe:1","-y",seed.to_string_lossy().as_ref()].into_iter().map(String::from));let audio_stage=if matches!(audio,&AudioSource::Loop(_)|&AudioSource::ConcatList(_)){"Strict 8.63: mux Original MP3 packets"}else{"Strict 8.63: mux Processed AAC packets"};let am=Instant::now();run_ffmpeg(app,job,started,timer,mux,audio_stage,74.0,12.0,final_duration,encoder,attempt,cancel).await?;let audio_mux_sec=am.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"strict-audio-mux",audio_mux_sec);emit_timing(app,&job.project.id,"audio-mux",audio_mux_sec);if let Ok(meta)=std::fs::metadata(&seed){let mb_s=(meta.len() as f64/1_048_576.0)/audio_mux_sec.max(0.001);let _=app.emit("engine-profile",json!({"id":job.project.id,"diskWriteMBs":mb_s}));}
  let total_frames=(final_duration*fps as f64).round().max(master_frames as f64) as usize;let _=app.emit("engine-profile",json!({"id":job.project.id,"physicalEncodedFrames":master_frames,"logicalFrames":total_frames,"manifestFrames":total_frames}));let mm=Instant::now();ensure_license_allowed()?;crate::mp4_manifest::expand_video_prefix_cycle(&seed,&seed,0,master_frames,total_frames)?;ensure_license_allowed()?;let manifest_seconds=mm.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"zero-copy-manifest",manifest_seconds);emit_timing(app,&job.project.id,"manifest-expand",manifest_seconds);let finalize_mark=Instant::now();finalize_local_output(&seed,out).map_err(|e|format!("Strict 8.64: finalize zero-copy MP4: {e}"))?;ensure_license_allowed()?;strict_856_validate_natural_size(out)?;ensure_license_allowed()?;emit_timing(app,&job.project.id,"finalize",finalize_mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,96.0,"Strict 8.64 zero-copy готов",encoder,attempt,None);Ok(true)
}

async fn render_periodic_zero_copy_852(app:&AppHandle,job:&QueueJob,effects:&[EffectPreset],subs:&[SubscribePreset],audio:&AudioSource,final_duration:f64,work:&Path,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<bool,String>{
  let Some(plan)=periodic_852_plan(job,effects,subs,final_duration) else{return Ok(false)};let fps=job.settings.fps.max(1) as usize;let sub_d=probe_duration(app,&plan.sub.effect.source).await.unwrap_or(0.0);let sub_frames=(sub_d*fps as f64).ceil().max(1.0) as usize;
  if plan.first_frames<plan.anchor_frames&&sub_frames>plan.anchor_frames-plan.first_frames{return Ok(false)}
  let periodic_total_mark=Instant::now();let master_mark=Instant::now();let master=build_periodic_master_852(app,job,effects,&plan,work,encoder,attempt,cancel,started,timer).await?;let master_sec=master_mark.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"periodic-master",master_sec);
  let mut prefix=Vec::<PathBuf>::new();
  if plan.first_frames<plan.anchor_frames{
    if plan.first_frames>0{let p=work.join("periodic-852-prefix-head.mp4");copy_head_frames_852(app,job,&master,plan.first_frames,&p,encoder,attempt,cancel,started,timer).await?;prefix.push(p)}
    let gap=plan.anchor_frames-plan.first_frames;let m=Instant::now();let p=render_periodic_sub_852(app,job,&master,&plan.sub,plan.first_frames,gap,work,"first",encoder,attempt,cancel,started,timer).await?;emit_timing(app,&job.project.id,"periodic-sub-first",m.elapsed().as_secs_f64());prefix.push(p);
  }else if plan.anchor_frames>0{let p=work.join("periodic-852-prefix-head.mp4");copy_head_frames_852(app,job,&master,plan.anchor_frames,&p,encoder,attempt,cancel,started,timer).await?;prefix.push(p)}
  let phase=plan.anchor_frames%plan.master_frames;let mut cycle_sub=(plan.master_frames-phase)%plan.master_frames;if cycle_sub==0{cycle_sub=plan.master_frames}while cycle_sub<sub_frames{cycle_sub+=plan.master_frames}if cycle_sub>=plan.repeat_frames{return Ok(false)}
  let recurring_mark=Instant::now();let recurring=render_periodic_sub_852(app,job,&master,&plan.sub,phase,cycle_sub,work,"cycle",encoder,attempt,cancel,started,timer).await?;emit_timing(app,&job.project.id,"periodic-sub-cycle",recurring_mark.elapsed().as_secs_f64());
  let mut parts=prefix;parts.push(recurring);let remain=plan.repeat_frames-cycle_sub;let full=remain/plan.master_frames;let tail=remain%plan.master_frames;for _ in 0..full{parts.push(master.clone())}if tail>0{let p=work.join("periodic-852-cycle-tail.mp4");copy_head_frames_852(app,job,&master,tail,&p,encoder,attempt,cancel,started,timer).await?;parts.push(p)}
  let seed_video=work.join("periodic-852-seed-video.mp4");let seed_frames=plan.anchor_frames+plan.repeat_frames;let concat_mark=Instant::now();concat_video_parts_852(app,job,&parts,&seed_video,seed_frames,work,encoder,attempt,cancel,started,timer).await?;emit_timing(app,&job.project.id,"periodic-video-concat",concat_mark.elapsed().as_secs_f64());
  let seed=work.join("periodic-852-seed.mp4");let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-i",seed_video.to_string_lossy().as_ref()].into_iter().map(String::from).collect();match audio{AudioSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::ConcatList(p)=>args.extend(vec!["-stream_loop","-1","-f","concat","-safe","0","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))};args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-progress","pipe:1","-y",seed.to_string_lossy().as_ref()].into_iter().map(String::from));let seed_mux_mark=Instant::now();run_ffmpeg(app,job,started,timer,args,"8.52: mux seed без размножения video payload",78.0,8.0,final_duration,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"periodic-seed-mux",seed_mux_mark.elapsed().as_secs_f64());
  let total_frames=(final_duration*fps as f64).round().max(seed_frames as f64) as usize;let _=app.emit("engine-profile",json!({"id":job.project.id,"physicalEncodedFrames":seed_frames,"logicalFrames":total_frames,"manifestFrames":total_frames}));let mark=Instant::now();ensure_license_allowed()?;crate::mp4_manifest::expand_video_prefix_cycle(&seed,&seed,plan.anchor_frames,plan.repeat_frames,total_frames)?;ensure_license_allowed()?;let manifest_seconds=mark.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"zero-copy-manifest",manifest_seconds);emit_timing(app,&job.project.id,"manifest-expand",manifest_seconds);let finalize_mark=Instant::now();finalize_local_output(&seed,out).map_err(|e|format!("8.64: не удалось завершить zero-copy MP4: {e}"))?;ensure_license_allowed()?;strict_856_validate_natural_size(out)?;ensure_license_allowed()?;emit_timing(app,&job.project.id,"finalize",finalize_mark.elapsed().as_secs_f64());emit_timing(app,&job.project.id,"periodic-total",periodic_total_mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,96.0,"8.64 Zero-copy manifest готов",encoder,attempt,None);Ok(true)
}

pub async fn render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<RenderOutcome,String>{
  ensure_license_allowed()?;
  let mut resolved_job=job.clone();refresh_project_paths(&mut resolved_job);
  let decision=fast_path_decision(&resolved_job);
  let _=app.emit("render-diagnostics",json!({"id":resolved_job.project.id,"fastPathEligible":decision.eligible,"fastPathReason":decision.reason,"mediaCount":resolved_job.project.media.len(),"imageCount":resolved_job.project.media.iter().filter(|m|is_image(m)).count(),"videoCount":resolved_job.project.media.iter().filter(|m|!is_image(m)).count(),"audioProcessingRequested":audio_processing_requested(&resolved_job)}));
  if smart_repeat_project(&resolved_job){
    if resolved_job.settings.width!=1920||resolved_job.settings.height!=1080{emit_warning(app,&resolved_job.project.id,"Fidelity Lock: fast static проект выводится строго 1920x1080 для компактного HEVC sample-table pipeline.");}
    resolved_job.settings.width=1920;
    resolved_job.settings.height=1080;
    resolved_job.settings.fps=60;
    resolved_job.settings.codec="h265".into();
    resolved_job.settings.duration_mode="whole-track".into();
  }
  let job=&resolved_job;let requested_audio_processing=audio_processing_requested(job);let scan_mark=Instant::now();
  for p in &job.project.media{if !Path::new(p).is_file(){return Err(format!("Не найден файл изображения/видео: {}",Path::new(p).file_name().and_then(|x|x.to_str()).unwrap_or(p)));}}
  for p in &job.project.audio{if !Path::new(p).is_file(){return Err(format!("Не найден аудиофайл: {}",Path::new(p).file_name().and_then(|x|x.to_str()).unwrap_or(p)));}}
  if job.project.media.is_empty(){return Err("В проекте нет изображения или видео".into())}
  if job.project.audio.is_empty(){return Err("В проекте нет музыки".into())}
  let scan_seconds=scan_mark.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"scan",scan_seconds);emit_timing(app,&job.project.id,"project-scan",scan_seconds);
  let started=chrono::Utc::now().timestamp_millis();let timer=Instant::now();let mut last_error=String::new();
  let ffmpeg_start=FFMPEG_LAUNCHES.load(Ordering::Relaxed);let ffprobe_start=FFPROBE_LAUNCHES.load(Ordering::Relaxed);
  let requested_out_dir=PathBuf::from(&job.settings.output_dir);let out_dir=resolve_output_dir(app,&requested_out_dir)?;if out_dir!=requested_out_dir{emit_warning(app,&job.project.id,&format!("Выбранная папка недоступна. Результат будет сохранён в {}",out_dir.display()));}
  let out=if smart_repeat_project(job){unique_output(&out_dir,&job.project.name)}else{unique_output(&out_dir,&job.project.name)};
  let max_attempts=if smart_repeat_project(job){if cfg!(target_os="windows"){2}else{1}}else{2};
  for attempt in 1..=max_attempts{
    if cancel.load(Ordering::SeqCst){return Err(CANCELLED.into())}
    let smart_repeat=smart_repeat_project(job);let _=std::fs::remove_file(&out);let encoder_mark=Instant::now();let encoder=if smart_repeat{let e=choose_hybrid_encoder(app,attempt).await;if !strict_856_encoder_allowed(&e){return Err(format!("Strict 8.63: HEVC encoder {e} недоступен для fast pipeline"))}e}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};let encoder_seconds=encoder_mark.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"encoder-benchmark",encoder_seconds);emit_timing(app,&job.project.id,"encoder-detection",encoder_seconds);
    let _=app.emit("engine-profile",json!({"id":job.project.id,"smartSize":smart_repeat,"smartRepeat":smart_repeat,"originalFidelity":smart_repeat,"fastPath":smart_repeat,"fastPathReason":decision.reason,"audioProcessingRequested":requested_audio_processing,"targetVideoKbps":None::<u64>}));
    emit_progress(app,job,started,&timer,1.0,"Анализ файлов",&encoder,attempt,None);let work=render_work_dir(app,&job.project.id,attempt)?;
    let result:Result<(Vec<f64>,f64,bool),String>=async{
      emit_progress(app,job,started,&timer,4.0,"Проверяю самый быстрый движок",&encoder,attempt,None);
      let (source_master,master_duration)=build_source_master(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
      let (fx,subs)=prepare_overlays(app,job,started,&timer,&encoder,attempt).await?;
      let visual_master_duration=if smart_repeat{smart_repeat_visual_seconds(app,master_duration,&fx).await}else{master_duration};
      let target=job.settings.duration_hours*3600.0;
      let (audio,durations,final_duration,original_audio)=if smart_repeat{
        let prefer_original=job.settings.duration_mode=="whole-track"&&job.ambient.as_ref().map(|x|x.trim().is_empty()).unwrap_or(true);
        if prefer_original{
          match build_original_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await{
            Ok((cycle,durations,_cycle_duration))=>{
              let final_duration=smart_final_duration(target,&durations,0.0,&job.settings.duration_mode);
              let direct_list=cycle.extension().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("txt")).unwrap_or(false);
              if requested_audio_processing{emit_warning(app,&job.project.id,"Strict Whole-Track Fidelity: совместимые MP3 сохраняются packet-copy целиком; crossfade/loudnorm пропущены, чтобы не перекодировать и не укорачивать песни.");}
              let _=app.emit("engine-profile",json!({"id":job.project.id,"audioOriginal":true,"audioLossless":true,"crossfadeApplied":false,"normalizeApplied":false,"audioDirectConcatList":direct_list}));
              (if direct_list{AudioSource::ConcatList(cycle)}else{AudioSource::Loop(cycle)},durations,final_duration,true)
            },
            Err(reason)=>{
              if !requested_audio_processing{return Err(format!("Strict Fidelity: исходную музыку нельзя сохранить bitstream-copy ({reason}). Используй MP3 с одинаковыми sample rate/channel layout."))}
              let audio_cycle_mark=Instant::now();let (cycle,durations,_cycle_duration)=build_lossless_processed_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;emit_timing(app,&job.project.id,"processed-audio-cycle",audio_cycle_mark.elapsed().as_secs_f64());
              let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,&job.settings.duration_mode);
              let audio_materialize_mark=Instant::now();let continuous=materialize_continuous_audio(app,job,started,&timer,&work,&cycle,final_duration,&encoder,attempt,&cancel).await?;emit_timing(app,&job.project.id,"processed-audio-materialize",audio_materialize_mark.elapsed().as_secs_f64());
              emit_warning(app,&job.project.id,&format!("Original MP3 packet-copy недоступен ({reason}); использую HQ processed fallback."));
              (AudioSource::Long(continuous),durations,final_duration,false)
            }
          }
        }else if requested_audio_processing{
          let audio_cycle_mark=Instant::now();let (cycle,durations,_cycle_duration)=build_lossless_processed_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;emit_timing(app,&job.project.id,"processed-audio-cycle",audio_cycle_mark.elapsed().as_secs_f64());
          let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,&job.settings.duration_mode);
          let audio_materialize_mark=Instant::now();let continuous=materialize_continuous_audio(app,job,started,&timer,&work,&cycle,final_duration,&encoder,attempt,&cancel).await?;emit_timing(app,&job.project.id,"processed-audio-materialize",audio_materialize_mark.elapsed().as_secs_f64());
          (AudioSource::Long(continuous),durations,final_duration,false)
        }else{
          let (cycle,durations,_cycle_duration)=build_original_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
          let final_duration=smart_final_duration(target,&durations,0.0,&job.settings.duration_mode);
          let direct_list=cycle.extension().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("txt")).unwrap_or(false);
          (if direct_list{AudioSource::ConcatList(cycle)}else{AudioSource::Loop(cycle)},durations,final_duration,true)
        }
      }else{
        let (cycle,durations,cycle_duration)=build_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
        let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,&job.settings.duration_mode);
        let audio=build_long_audio(app,job,started,&timer,&work,&cycle,cycle_duration,final_duration,&encoder,attempt,&cancel).await?;
        (audio,durations,final_duration,false)
      };
      let zero_copy=if smart_repeat{
        if render_multi_still_zero_copy_863(app,job,&audio,final_duration,&work,&out,&encoder,attempt,&cancel,started,&timer).await?{true}
        else if render_zero_sub_zero_copy_856(app,job,&fx,&subs,&audio,visual_master_duration,final_duration,&work,&out,&encoder,attempt,&cancel,started,&timer).await?{true}
        else{render_periodic_zero_copy_852(app,job,&fx,&subs,&audio,final_duration,&work,&out,&encoder,attempt,&cancel,started,&timer).await?}
      }else{false};
      if smart_repeat&&!zero_copy{return Err("Strict 8.56: этот Subscribe schedule не поддерживает безопасный zero-copy профиль; медленный многочасовой fallback запрещён".into())}
      if !zero_copy{
        let visual=assemble_visual(app,job,&source_master,visual_master_duration,&fx,&subs,final_duration,&work,&encoder,attempt,&cancel,started,&timer).await?;
        let mux_mark=Instant::now();let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
        match visual{VisualSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),VisualSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),VisualSource::Concat(p)=>args.extend(vec!["-f","concat","-safe","0","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}
        match &audio{AudioSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::ConcatList(p)=>args.extend(vec!["-stream_loop","-1","-f","concat","-safe","0","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}
        args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-movflags","+faststart","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
        run_ffmpeg(app,job,started,&timer,args,"Собираю итоговое видео",90.0,6.0,final_duration,&encoder,attempt,&cancel).await?;emit_timing(app,&job.project.id,"final-mux",mux_mark.elapsed().as_secs_f64());
      }
      ensure_license_allowed()?;emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&encoder,attempt,None);let verify_mark=Instant::now();verify_result(app,&out,final_duration,&job.settings).await?;if smart_repeat{verify_strict_857_result(app,&out,final_duration,original_audio,&durations).await?;}let validation_seconds=verify_mark.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"ffprobe-validation",validation_seconds);emit_timing(app,&job.project.id,"validation",validation_seconds);ensure_license_allowed()?;
      let result_stem=out.file_stem().and_then(|x|x.to_str()).unwrap_or(&job.project.name);let side_mark=Instant::now();if let Err(err)=write_side_files(job,&out_dir,&durations,final_duration,result_stem){emit_warning(app,&job.project.id,&format!("Видео готово, но служебные файлы не записаны: {err}"));}emit_timing(app,&job.project.id,"side-files",side_mark.elapsed().as_secs_f64());ensure_license_allowed()?;
      Ok((durations,final_duration,original_audio))
    }.await;
    match result{
      Ok((_durations,fd,original_audio))=>{
        if let Err(e)=ensure_license_allowed(){let _=std::fs::remove_dir_all(&work);let _=std::fs::remove_file(&out);return Err(e)}
        let bytes=std::fs::metadata(&out).ok().map(|m|m.len());let bitrate=probe_video_bitrate(app,&out).await;
        let codec_args=vec!["-v","error","-show_entries","stream=codec_type,codec_name","-of","json",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
        let (video_codec,audio_codec)=match output(app,"ffprobe",codec_args).await{
          Ok((raw,_))=>{let v:serde_json::Value=serde_json::from_slice(&raw).unwrap_or_else(|_|json!({}));let streams=v.get("streams").and_then(|x|x.as_array()).cloned().unwrap_or_default();let vc=streams.iter().find(|x|x.get("codec_type").and_then(|y|y.as_str())==Some("video")).and_then(|x|x.get("codec_name")).and_then(|x|x.as_str()).unwrap_or("unknown").to_string();let ac=streams.iter().find(|x|x.get("codec_type").and_then(|y|y.as_str())==Some("audio")).and_then(|x|x.get("codec_name")).and_then(|x|x.as_str()).unwrap_or("unknown").to_string();(vc,ac)},
          Err(_)=>("unknown".into(),"unknown".into())
        };
        if let Err(e)=ensure_license_allowed(){let _=std::fs::remove_dir_all(&work);let _=std::fs::remove_file(&out);return Err(e)}
        let elapsed=timer.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"total",elapsed);
        let ffmpeg_launches=FFMPEG_LAUNCHES.load(Ordering::Relaxed).saturating_sub(ffmpeg_start);let ffprobe_launches=FFPROBE_LAUNCHES.load(Ordering::Relaxed).saturating_sub(ffprobe_start);let _=app.emit("engine-profile",json!({"id":job.project.id,"ffmpegLaunches":ffmpeg_launches,"ffprobeLaunches":ffprobe_launches,"logicalFrames":(fd*job.settings.fps as f64).round().max(1.0) as u64,"finalBytes":bytes,"finalDuration":fd,"numberOfImages":job.project.media.len(),"numberOfTracks":job.project.audio.len()}));
        let result_path=out.to_string_lossy().into_owned();
        let _=app.emit("render-done",Progress{id:job.project.id.clone(),status:"done".into(),progress:100.0,stage:"Готово".into(),started_at:Some(started),elapsed_sec:elapsed,eta_sec:Some(0.0),result_path:Some(result_path.clone()),result_bytes:bytes,actual_video_bitrate:bitrate,cpu_pct:None,ram_bytes:None,ram_total_bytes:None,ram_available_bytes:None,gpu_pct:None,encoder:Some(encoder.clone()),attempt:Some(attempt)});
        let outcome=RenderOutcome{output_path:result_path,output_bytes:bytes,encoder:encoder.clone(),final_video_duration_seconds:fd,fast_path:smart_repeat,fast_path_reason:decision.reason.to_string(),audio_mode:if original_audio{"ORIGINAL_MP3_PACKET_COPY".into()}else{"PROCESSED_AUDIO".into()},video_codec,audio_codec};
        let _=std::fs::remove_dir_all(&work);return Ok(outcome)
      },
      Err(e)=>{last_error=e;if smart_repeat&&attempt==1{invalidate_hybrid_encoder_cache(app);}emit_warning(app,&job.project.id,&format!("Попытка {attempt} не прошла: {last_error}"));let _=std::fs::remove_dir_all(&work);let _=std::fs::remove_file(&out);if last_error==CANCELLED{return Err(last_error)}if attempt<max_attempts{emit_progress(app,job,started,&timer,2.0,"Повторяю безопасную попытку",&encoder,attempt+1,None);}}
    }
  }
  Err(last_error)
}
