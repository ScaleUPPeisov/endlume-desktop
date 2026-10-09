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

#[tauri::command]
pub async fn generate_preview(app:AppHandle,project_path:String,time_sec:f64,effects:Vec<EffectPreset>,subscribes:Vec<SubscribePreset>)->Result<String,String>{
  let dir=PathBuf::from(&project_path);if !dir.is_dir(){return Err("Сначала выберите папку проекта".into())}
  let mut media:Vec<PathBuf>=std::fs::read_dir(&dir).map_err(|e|e.to_string())?.flatten().map(|e|e.path()).filter(|p|p.is_file()&&(IMAGE.contains(&ext(p).as_str())||VIDEO.contains(&ext(p).as_str()))).collect();media.sort_by(|a,b|natural_name(a).cmp(&natural_name(b)));
  let (src,local_time)=pick_preview_media(&media,time_sec).ok_or("В проекте нет изображения или видео")?;
  let preview_dir=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("previews");std::fs::create_dir_all(&preview_dir).map_err(|e|e.to_string())?;let out=preview_dir.join(format!("endlume-preview-{}.mp4",uuid::Uuid::new_v4()));
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
  if is_image(src){args.extend(vec!["-loop","1","-i",src.to_string_lossy().as_ref()].into_iter().map(String::from));}else{args.extend(vec!["-stream_loop","-1","-ss",&local_time.max(0.0).to_string(),"-i",src.to_string_lossy().as_ref()].into_iter().map(String::from));}
  let enabled_fx:Vec<EffectPreset>=visual_spec::active_effects_at(&effects,time_sec.max(0.0),365.0*24.0*3600.0);
  let enabled_sub:Vec<SubscribePreset>=subscribes.into_iter().filter(|e|e.effect.enabled&&!e.effect.source.trim().is_empty()).collect();
  let mut all=enabled_fx.clone();all.extend(enabled_sub.iter().map(|s|s.effect.clone()));
  for e in &all{args.extend(vec!["-stream_loop","-1","-ss",&e.preview_frame_time.max(0.0).to_string(),"-i",e.source.as_str()].into_iter().map(String::from));}
  let graph=format!("{}[b0]",visual_spec::base_filter("0:v",1280,720,60));let (mut graph,last)=visual_spec::apply_effects_filter(graph,"b0".into(),&all,1280,720,60,1);graph.push_str(&format!(";[{last}]format=yuv420p[outv]"));
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t","6","-an","-c:v","libx264","-preset","ultrafast","-crf","18","-pix_fmt","yuv420p","-movflags","+faststart","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  let output=app.shell().sidecar("ffmpeg").map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  if !output.status.success(){let err=String::from_utf8_lossy(&output.stderr).trim().to_string();return Err(if err.is_empty(){"FFmpeg не смог собрать предпросмотр".into()}else{err})}
  Ok(out.to_string_lossy().into_owned())
}
