use serde::Serialize;
use sha2::{Digest,Sha256};
use std::{fs,io::Read,path::{Path,PathBuf},time::UNIX_EPOCH};
use tauri::{AppHandle,Manager};
use tauri_plugin_shell::ShellExt;
use walkdir::WalkDir;

const IMAGE:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];
const VIDEO:&[&str]=&["mp4","mov","m4v","mkv","webm","avi","wmv","flv","ts","mts","m2ts","mpg","mpeg","vob","3gp"];

#[derive(Serialize)]
#[serde(rename_all="camelCase")]
pub struct LivePreviewAssets{base_path:String,base_kind:String,overlay_path:String}

fn ext(p:&Path)->String{p.extension().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase()}
fn is_macos_sidecar(p:&Path)->bool{let n=p.file_name().and_then(|x|x.to_str()).unwrap_or("");n==".DS_Store"||n.starts_with("._")||n.starts_with(".Spotlight-")||n.starts_with(".Trashes")||n.starts_with('.')}
fn has_appledouble_magic(p:&Path)->bool{let mut b=[0u8;4];fs::File::open(p).and_then(|mut f|f.read_exact(&mut b)).is_ok()&&matches!(u32::from_be_bytes(b),0x00051607|0x00051600)}
fn rejected_macos_input(p:&Path)->bool{is_macos_sidecar(p)||has_appledouble_magic(p)}
fn is_image(p:&Path)->bool{IMAGE.contains(&ext(p).as_str())}
fn is_media(p:&Path)->bool{is_image(p)||VIDEO.contains(&ext(p).as_str())}
fn natural_name(p:&Path)->String{p.file_name().and_then(|x|x.to_str()).unwrap_or("").to_lowercase()}
fn ready_file(p:&Path)->bool{!is_macos_sidecar(p)&&fs::metadata(p).map(|m|m.is_file()&&m.len()>1024).unwrap_or(false)}

fn json_positive(v:Option<&serde_json::Value>)->bool{
  v.and_then(|x|x.as_f64().or_else(||x.as_str().and_then(|s|s.parse::<f64>().ok()))).map(|x|x.is_finite()&&x>0.0).unwrap_or(false)
}
fn proxy_probe_valid(raw:&[u8])->bool{
  let Ok(v)=serde_json::from_slice::<serde_json::Value>(raw) else{return false};
  let Some(stream)=v.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()) else{return false};
  if stream.get("codec_type").and_then(|x|x.as_str())!=Some("video"){return false}
  if !json_positive(stream.get("width"))||!json_positive(stream.get("height")){return false}
  json_positive(v.get("format").and_then(|x|x.get("duration")))
}
fn accept_proxy_attempt(process_ok:bool,proxy_valid:bool)->bool{process_ok&&proxy_valid}

fn cache_dir(app:&AppHandle)->Result<PathBuf,String>{let dir=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("live-preview-v6");fs::create_dir_all(&dir).map_err(|e|e.to_string())?;Ok(dir)}
fn fingerprint(path:&Path,seek:f64,kind:&str)->String{let meta=fs::metadata(path).ok();let size=meta.as_ref().map(|m|m.len()).unwrap_or(0);let modified=meta.as_ref().and_then(|m|m.modified().ok()).and_then(|t|t.duration_since(UNIX_EPOCH).ok()).map(|d|d.as_secs()).unwrap_or(0);let mut h=Sha256::new();h.update(format!("{}|{}|{}|{:.2}|{}",path.to_string_lossy(),size,modified,seek,kind));hex::encode(h.finalize())[..24].to_string()}
fn first_media(project:&Path)->Option<PathBuf>{let mut files=WalkDir::new(project).max_depth(3).into_iter().filter_map(Result::ok).map(|e|e.into_path()).filter(|p|p.is_file()&&!rejected_macos_input(p)&&is_media(p)&&ready_file(p)).collect::<Vec<_>>();files.sort_by(|a,b|natural_name(a).cmp(&natural_name(b)));files.into_iter().next()}

async fn run(app:&AppHandle,args:Vec<String>)->Result<(),String>{let out=app.shell().sidecar("ffmpeg").map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;if out.status.success(){Ok(())}else{Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}}

async fn validate_video_proxy(app:&AppHandle,out:&Path)->Result<(),String>{
  if !ready_file(out){return Err("proxy-файл отсутствует или слишком мал".into())}
  let probe_args=vec!["-v","error","-select_streams","v:0","-show_entries","stream=codec_type,width,height:format=duration","-of","json",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();
  let probe=app.shell().sidecar("ffprobe").map_err(|e|format!("FFprobe Live Preview недоступен: {e}"))?.args(probe_args).output().await.map_err(|e|format!("Не удалось запустить FFprobe Live Preview: {e}"))?;
  if !probe.status.success(){return Err(format!("FFprobe не принял proxy: {}",String::from_utf8_lossy(&probe.stderr).trim()))}
  if !proxy_probe_valid(&probe.stdout){return Err("FFprobe не подтвердил video stream / geometry / duration".into())}
  let decode_args=vec!["-hide_banner","-loglevel","error","-ss","0","-i",out.to_string_lossy().as_ref(),"-map","0:v:0","-frames:v","1","-f","null","-"].into_iter().map(String::from).collect();
  run(app,decode_args).await.map_err(|e|format!("proxy не декодируется: {e}"))?;
  Ok(())
}

async fn proxy_attempt(app:&AppHandle,prefix:&[String],codec:Vec<String>,out:&Path)->Result<(),String>{
  let _=fs::remove_file(out);
  let mut args=prefix.to_vec();args.extend(codec);args.extend(vec!["-movflags","+faststart","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  let process=run(app,args).await;
  let validation=if process.is_ok(){validate_video_proxy(app,out).await}else{Err("FFmpeg process failed".into())};
  if accept_proxy_attempt(process.is_ok(),validation.is_ok()){return Ok(())}
  let process_error=process.err().unwrap_or_else(||"FFmpeg exit=0".into());
  let validation_error=validation.err().unwrap_or_else(||"proxy validation passed".into());
  Err(format!("{process_error}; validation: {validation_error}"))
}

fn hardware_codec_args()->Vec<String>{
  #[cfg(target_os="macos")]
  {vec!["-c:v","h264_videotoolbox","-realtime","1","-q:v","72","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()}
  #[cfg(not(target_os="macos"))]
  {vec!["-c:v","libx264","-preset","ultrafast","-crf","18","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()}
}
fn software_codec_args()->Vec<String>{vec!["-c:v","libx264","-preset","ultrafast","-crf","18","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()}

async fn encode_proxy(app:&AppHandle,prefix:Vec<String>,safe_prefix:Option<Vec<String>>,out:&Path)->Result<(),String>{
  let hw=proxy_attempt(app,&prefix,hardware_codec_args(),out).await;
  if hw.is_ok(){return Ok(())}
  let hw_error=hw.err().unwrap_or_else(||"unknown hardware preview failure".into());
  #[cfg(target_os="macos")]
  {
    let sw=proxy_attempt(app,&prefix,software_codec_args(),out).await;
    if sw.is_ok(){return Ok(())}
    let sw_error=sw.err().unwrap_or_else(||"unknown libx264 preview failure".into());
    if let Some(safe)=safe_prefix{
      let safe_result=proxy_attempt(app,&safe,software_codec_args(),out).await;
      if safe_result.is_ok(){return Ok(())}
      let safe_error=safe_result.err().unwrap_or_else(||"unknown safe preview failure".into());
      let _=fs::remove_file(out);
      return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}; safe fps fallback: {safe_error}"))
    }
    let _=fs::remove_file(out);
    Err(format!("VideoToolbox Live Preview: {hw_error}; libx264 fallback: {sw_error}"))
  }
  #[cfg(not(target_os="macos"))]
  {
    let _=fs::remove_file(out);
    Err(hw_error)
  }
}

async fn make_base(app:&AppHandle,src:&Path,seek:f64,out:&Path)->Result<String,String>{
  if is_image(src){
    if ready_file(out){return Ok("image".into())}
    let _=fs::remove_file(out);
    let args=vec!["-hide_banner","-loglevel","error","-i",src.to_string_lossy().as_ref(),"-vf","scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2","-frames:v","1","-q:v","2","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
    run(app,args).await?;if !ready_file(out){return Err("Не удалось создать базовый кадр Live Preview".into())}Ok("image".into())
  }else{
    if validate_video_proxy(app,out).await.is_ok(){return Ok("video".into())}
    let _=fs::remove_file(out);
    let prefix=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&seek.max(0.0).to_string(),"-i",src.to_string_lossy().as_ref(),"-t","5","-an","-vf","scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2,fps=30"].into_iter().map(String::from).collect();
    encode_proxy(app,prefix,None,out).await?;Ok("video".into())
  }
}

async fn make_overlay(app:&AppHandle,src:&Path,seek:f64,out:&Path)->Result<(),String>{
  if validate_video_proxy(app,out).await.is_ok(){return Ok(())}
  let _=fs::remove_file(out);
  let common=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&seek.max(0.0).to_string(),"-i",src.to_string_lossy().as_ref(),"-t","6","-an","-vf"];
  let mut prefix=common.iter().map(|x|String::from(*x)).collect::<Vec<_>>();
  prefix.push("scale=640:-2:flags=fast_bilinear,minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1".into());
  let mut safe=common.into_iter().map(String::from).collect::<Vec<_>>();
  safe.push("scale=640:-2:flags=lanczos,fps=60".into());
  encode_proxy(app,prefix,Some(safe),out).await
}

#[tauri::command]
pub async fn prepare_live_preview(app:AppHandle,project_path:String,overlay_source:String,time_sec:f64)->Result<LivePreviewAssets,String>{
  let project=PathBuf::from(project_path);if !project.is_dir(){return Err("Сначала выберите папку проекта".into())}
  let overlay=PathBuf::from(overlay_source);if !overlay.is_file(){return Err("Не найден файл Effects/Subscribe".into())}if rejected_macos_input(&overlay){return Err("ENDLUME заблокировала служебный AppleDouble/resource-fork файл macOS. Выберите настоящий Effects/Subscribe файл.".into())}if rejected_macos_input(&overlay){return Err("ENDLUME заблокировала служебный AppleDouble/resource-fork файл macOS. Выберите настоящий Effects/Subscribe файл.".into())}
  let base=first_media(&project).ok_or("В проекте нет корректного изображения или видео")?;let dir=cache_dir(&app)?;
  let base_key=fingerprint(&base,time_sec,"base");let overlay_key=fingerprint(&overlay,time_sec,"overlay");
  let base_out=if is_image(&base){dir.join(format!("base-{base_key}.jpg"))}else{dir.join(format!("base-{base_key}.mp4"))};let overlay_out=dir.join(format!("overlay-{overlay_key}.mp4"));
  let base_kind=make_base(&app,&base,time_sec,&base_out).await?;make_overlay(&app,&overlay,time_sec,&overlay_out).await?;
  Ok(LivePreviewAssets{base_path:base_out.to_string_lossy().into_owned(),base_kind,overlay_path:overlay_out.to_string_lossy().into_owned()})
}

#[cfg(test)]
mod tests{
  use super::*;

  #[test]
  fn hardware_success_with_valid_proxy_is_accepted(){assert!(accept_proxy_attempt(true,true));}

  #[test]
  fn hardware_exit_zero_with_invalid_proxy_requires_fallback(){assert!(!accept_proxy_attempt(true,false));}

  #[test]
  fn hardware_process_failure_requires_fallback(){assert!(!accept_proxy_attempt(false,false));}

  #[test]
  fn libx264_success_with_valid_proxy_is_accepted(){assert!(accept_proxy_attempt(true,true));}

  #[test]
  fn ffprobe_contract_requires_video_geometry_and_duration(){
    let good=br#"{"streams":[{"codec_type":"video","width":640,"height":360}],"format":{"duration":"6.000000"}}"#;
    let no_stream=br#"{"streams":[],"format":{"duration":"6.000000"}}"#;
    let no_duration=br#"{"streams":[{"codec_type":"video","width":640,"height":360}],"format":{"duration":"0"}}"#;
    assert!(proxy_probe_valid(good));assert!(!proxy_probe_valid(no_stream));assert!(!proxy_probe_valid(no_duration));
  }
}
