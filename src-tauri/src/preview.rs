use crate::{model::{EffectPreset,SubscribePreset},visual_spec};
use std::path::{Path,PathBuf};
use tauri::{AppHandle,Manager};
use tauri_plugin_shell::ShellExt;

const IMAGE:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];
const VIDEO:&[&str]=&["mp4","mov","m4v","mkv","webm","avi","wmv","flv","ts","mts","m2ts","mpg","mpeg","vob","3gp"];
fn ext(p:&Path)->String{p.extension().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase()}
fn is_image(p:&Path)->bool{IMAGE.contains(&ext(p).as_str())}
fn natural_name(p:&PathBuf)->(u64,String){let s=p.file_name().and_then(|x|x.to_str()).unwrap_or("").to_lowercase();let digits=s.chars().skip_while(|c|!c.is_ascii_digit()).take_while(|c|c.is_ascii_digit()).collect::<String>();(digits.parse::<u64>().unwrap_or(u64::MAX),s)}
fn pick_preview_media(media:&[PathBuf],time_sec:f64)->Option<(&PathBuf,f64)>{if media.is_empty(){return None}let slot=10.0_f64;let t=time_sec.max(0.0);let idx=((t/slot).floor() as usize)%media.len();Some((&media[idx],t%slot))}

async fn probe_duration(app:&AppHandle,path:&str)->Option<f64>{
  let out=app.shell().sidecar("ffprobe").ok()?.args(vec!["-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",path]).output().await.ok()?;
  if !out.status.success(){return None}
  String::from_utf8_lossy(&out.stdout).trim().parse::<f64>().ok().filter(|d|d.is_finite()&&*d>0.0)
}
fn subscribe_phase(s:&SubscribePreset,t:f64,d:f64)->Option<f64>{
  let mut starts=Vec::new();for x in [s.first_at_sec,s.second_at_sec]{if x>=0.0&&!starts.iter().any(|v:&f64|(*v-x).abs()<0.001){starts.push(x)}}
  if s.repeat_every_sec>0.001{let base=s.second_at_sec.max(s.first_at_sec)+s.repeat_every_sec;if t>=base{let n=((t-base)/s.repeat_every_sec).floor();starts.push(base+n*s.repeat_every_sec);}}
  starts.into_iter().filter(|start|t>=*start&&t<*start+d).max_by(|a,b|a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal)).map(|start|(t-start).max(0.0))
}

#[tauri::command]
pub async fn generate_preview(app:AppHandle,project_path:String,time_sec:f64,effects:Vec<EffectPreset>,subscribes:Vec<SubscribePreset>)->Result<String,String>{
  let dir=PathBuf::from(&project_path);if !dir.is_dir(){return Err("Сначала выберите папку проекта".into())}
  let mut media:Vec<PathBuf>=std::fs::read_dir(&dir).map_err(|e|e.to_string())?.flatten().map(|e|e.path()).filter(|p|p.is_file()&&(IMAGE.contains(&ext(p).as_str())||VIDEO.contains(&ext(p).as_str()))).collect();media.sort_by(|a,b|natural_name(a).cmp(&natural_name(b)));
  let t=time_sec.max(0.0);let (src,local_time)=pick_preview_media(&media,t).ok_or("В проекте нет изображения или видео")?;
  let preview_dir=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("previews");std::fs::create_dir_all(&preview_dir).map_err(|e|e.to_string())?;let out=preview_dir.join(format!("endlume-preview-{}.mp4",uuid::Uuid::new_v4()));
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
  if is_image(src){args.extend(vec!["-loop","1","-framerate","60","-i",src.to_string_lossy().as_ref()].into_iter().map(String::from));}else{args.extend(vec!["-stream_loop","-1","-ss",&local_time.to_string(),"-i",src.to_string_lossy().as_ref()].into_iter().map(String::from));}

  let mut active=Vec::<EffectPreset>::new();let mut phases=Vec::<f64>::new();
  for e in visual_spec::active_effects_at(&effects,t,365.0*24.0*3600.0){let d=probe_duration(&app,&e.source).await.unwrap_or(5.0).max(0.001);phases.push(visual_spec::effect_phase_at(t,&e,d));active.push(e);}
  for s in subscribes.into_iter().filter(|s|s.effect.enabled&&!s.effect.source.trim().is_empty()){
    let d=probe_duration(&app,&s.effect.source).await.unwrap_or(5.0).max(0.001);if let Some(phase)=subscribe_phase(&s,t,d){phases.push(phase);active.push(s.effect);}
  }
  for (e,phase) in active.iter().zip(phases.iter()){args.extend(vec!["-stream_loop","-1","-ss",&phase.to_string(),"-i",e.source.as_str()].into_iter().map(String::from));}
  let graph=format!("{}[b0]",visual_spec::base_filter("0:v",1280,720,60));let (mut graph,last)=visual_spec::apply_effects_filter(graph,"b0".into(),&active,1280,720,60,1);graph.push_str(&format!(";[{last}]format=yuv420p[outv]"));
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t","2","-an","-c:v","libx264","-preset","ultrafast","-crf","18","-pix_fmt","yuv420p","-movflags","+faststart","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  let output=app.shell().sidecar("ffmpeg").map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  if !output.status.success(){let err=String::from_utf8_lossy(&output.stderr).trim().to_string();return Err(if err.is_empty(){"FFmpeg не смог собрать предпросмотр".into()}else{err})}
  Ok(out.to_string_lossy().into_owned())
}
