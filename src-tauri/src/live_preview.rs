use serde::Serialize;
use sha2::{Digest,Sha256};
use std::{fs,path::{Path,PathBuf},time::UNIX_EPOCH};
use tauri::{AppHandle,Manager};
use tauri_plugin_shell::ShellExt;
use walkdir::WalkDir;

const IMAGE:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];
const VIDEO:&[&str]=&["mp4","mov","m4v","mkv","webm","avi","wmv","flv","ts","mts","m2ts","mpg","mpeg","vob","3gp"];

#[derive(Serialize)]
#[serde(rename_all="camelCase")]
pub struct LivePreviewAssets{
  base_path:String,
  base_kind:String,
  overlay_path:String,
}

fn ext(p:&Path)->String{p.extension().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase()}
fn is_image(p:&Path)->bool{IMAGE.contains(&ext(p).as_str())}
fn is_media(p:&Path)->bool{is_image(p)||VIDEO.contains(&ext(p).as_str())}
fn natural_name(p:&Path)->String{p.file_name().and_then(|x|x.to_str()).unwrap_or("").to_lowercase()}

fn cache_dir(app:&AppHandle)->Result<PathBuf,String>{
  let dir=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("live-preview-v3");
  fs::create_dir_all(&dir).map_err(|e|e.to_string())?;Ok(dir)
}

fn fingerprint(path:&Path,seek:f64,kind:&str)->String{
  let meta=fs::metadata(path).ok();
  let size=meta.as_ref().map(|m|m.len()).unwrap_or(0);
  let modified=meta.as_ref().and_then(|m|m.modified().ok()).and_then(|t|t.duration_since(UNIX_EPOCH).ok()).map(|d|d.as_secs()).unwrap_or(0);
  let mut h=Sha256::new();h.update(format!("{}|{}|{}|{:.2}|{}",path.to_string_lossy(),size,modified,seek,kind));hex::encode(h.finalize())[..24].to_string()
}

fn first_media(project:&Path)->Option<PathBuf>{
  let mut files=WalkDir::new(project).max_depth(3).into_iter().filter_map(Result::ok).map(|e|e.into_path()).filter(|p|p.is_file()&&is_media(p)).collect::<Vec<_>>();
  files.sort_by(|a,b|natural_name(a).cmp(&natural_name(b)));files.into_iter().next()
}

async fn run(app:&AppHandle,args:Vec<String>)->Result<(),String>{
  let out=app.shell().sidecar("ffmpeg").map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  if out.status.success(){Ok(())}else{Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
}

fn video_codec_args()->Vec<String>{
  #[cfg(target_os="macos")]
  {vec!["-c:v","h264_videotoolbox","-realtime","1","-q:v","72","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()}
  #[cfg(not(target_os="macos"))]
  {vec!["-c:v","libx264","-preset","ultrafast","-crf","18","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()}
}

async fn make_base(app:&AppHandle,src:&Path,seek:f64,out:&Path)->Result<String,String>{
  if out.exists(){return Ok(if is_image(src){"image".into()}else{"video".into()})}
  if is_image(src){
    let args=vec!["-hide_banner","-loglevel","error","-i",src.to_string_lossy().as_ref(),"-vf","scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2","-frames:v","1","-q:v","2","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
    run(app,args).await?;Ok("image".into())
  }else{
    let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&seek.max(0.0).to_string(),"-i",src.to_string_lossy().as_ref(),"-t","5","-an","-vf","scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2,fps=30"].into_iter().map(String::from).collect();
    args.extend(video_codec_args());args.extend(vec!["-movflags","+faststart","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));run(app,args).await?;Ok("video".into())
  }
}

async fn make_overlay(app:&AppHandle,src:&Path,seek:f64,out:&Path)->Result<(),String>{
  if out.exists(){return Ok(())}
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&seek.max(0.0).to_string(),"-i",src.to_string_lossy().as_ref(),"-t","6","-an","-vf","scale=640:-2:flags=fast_bilinear,fps=60"].into_iter().map(String::from).collect();
  args.extend(video_codec_args());args.extend(vec!["-movflags","+faststart","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));run(app,args).await
}

#[tauri::command]
pub async fn prepare_live_preview(app:AppHandle,project_path:String,overlay_source:String,time_sec:f64)->Result<LivePreviewAssets,String>{
  let project=PathBuf::from(project_path);if !project.is_dir(){return Err("Сначала выберите папку проекта".into())}
  let overlay=PathBuf::from(overlay_source);if !overlay.is_file(){return Err("Не найден файл Effects/Subscribe".into())}
  let base=first_media(&project).ok_or("В проекте нет изображения или видео")?;let dir=cache_dir(&app)?;
  let base_key=fingerprint(&base,time_sec,"base");let overlay_key=fingerprint(&overlay,time_sec,"overlay");
  let base_out=if is_image(&base){dir.join(format!("base-{base_key}.jpg"))}else{dir.join(format!("base-{base_key}.mp4"))};
  let overlay_out=dir.join(format!("overlay-{overlay_key}.mp4"));
  let base_kind=make_base(&app,&base,time_sec,&base_out).await?;make_overlay(&app,&overlay,time_sec,&overlay_out).await?;
  Ok(LivePreviewAssets{base_path:base_out.to_string_lossy().into_owned(),base_kind,overlay_path:overlay_out.to_string_lossy().into_owned()})
}
