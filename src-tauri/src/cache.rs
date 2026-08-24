use crate::model::EffectPreset;
use serde_json::json;
use sha2::{Digest,Sha256};
use std::{fs,path::{Path,PathBuf},time::UNIX_EPOCH};
use tauri::{AppHandle,Emitter,Manager};
use tauri_plugin_shell::ShellExt;

fn color(hex:&str)->String{format!("0x{}",hex.trim().trim_start_matches('#').trim_start_matches("0x"))}

fn cache_dir(app:&AppHandle)->Result<PathBuf,String>{
  // v3 intentionally invalidates old chromakey caches created with the previous
  // YUV chromakey path. New cache uses RGB colorkey so kept pixels preserve source colour.
  let p=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("effects-v3-fidelity");
  fs::create_dir_all(&p).map_err(|e|e.to_string())?;
  Ok(p)
}

fn fingerprint(e:&EffectPreset,fps:u32)->String{
  let meta=fs::metadata(&e.source).ok();
  let modified=meta.as_ref().and_then(|m|m.modified().ok()).and_then(|t|t.duration_since(UNIX_EPOCH).ok()).map(|d|d.as_secs()).unwrap_or(0);
  let size=meta.as_ref().map(|m|m.len()).unwrap_or(0);
  let mut h=Sha256::new();
  h.update(format!("fidelity-v3|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",e.source,size,modified,fps,e.mode,e.key_color,e.similarity,e.blend,e.luma_threshold,e.luma_tolerance,e.saturation,e.scale,e.fullscreen));
  hex::encode(h.finalize())[..24].to_string()
}

pub async fn prepare(app:&AppHandle,e:&EffectPreset,fps:u32)->Result<EffectPreset,String>{
  if !e.enabled||e.source.trim().is_empty(){return Ok(e.clone())}
  if !Path::new(&e.source).is_file(){return Err(format!("Не найден файл эффекта: {}",e.source))}
  let key=fingerprint(e,fps);let path=cache_dir(app)?.join(format!("{}.mov",key));
  if !path.exists(){
    let prescale=if e.fullscreen||e.mode=="screen"{String::new()}else{format!(",scale=iw*{}:ih*{}",e.scale.max(0.01),e.scale.max(0.01))};
    let similarity=e.similarity.clamp(0.001,0.60);let blend=e.blend.clamp(0.001,0.35);
    let vf=match e.mode.as_str(){
      "luma"=>format!("fps={fps},format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08{prescale},format=argb",e.luma_threshold,e.luma_tolerance),
      "screen"=>format!("fps={fps},format=rgb24"),
      // colorkey works in RGB. Unlike the old chromakey path this does not alter
      // the RGB values of pixels that remain visible, so the rendered overlay
      // keeps the same colours as the source and the WebGL preview.
      _=>format!("fps={fps},format=rgba,colorkey={}:{}:{}{prescale},format=argb",color(&e.key_color),similarity,blend)
    };
    let pix=if e.mode=="screen"{"rgb24"}else{"argb"};
    let args=vec!["-hide_banner","-loglevel","error","-i",e.source.as_str(),"-vf",vf.as_str(),"-an","-c:v","qtrle","-pix_fmt",pix,"-y",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();
    let out=app.shell().sidecar("ffmpeg").map_err(|x|x.to_string())?.args(args).output().await.map_err(|x|x.to_string())?;
    if !out.status.success(){return Err(format!("Не удалось подготовить кэш '{}': {}",e.name,String::from_utf8_lossy(&out.stderr).trim()))}
  }
  let mut prepared=e.clone();prepared.source=path.to_string_lossy().into_owned();prepared.cache_key=Some(key.clone());prepared.cache_ready=Some(true);
  prepared.mode=if e.mode=="screen"{"screen-cache".into()}else{"prealpha".into()};
  if !e.fullscreen&&e.mode!="screen"{prepared.scale=1.0;}
  let _=app.emit("cache-updated",json!({"id":e.id,"cacheKey":key,"cacheReady":true}));
  Ok(prepared)
}

#[tauri::command]
pub fn cache_stats(app:AppHandle)->serde_json::Value{
  let dir=cache_dir(&app).ok();let mut count=0u64;let mut bytes=0u64;
  if let Some(dir)=dir{if let Ok(rd)=fs::read_dir(dir){for e in rd.flatten(){if let Ok(m)=e.metadata(){if m.is_file(){count+=1;bytes+=m.len();}}}}}
  json!({"count":count,"bytes":bytes})
}

#[tauri::command]
pub fn clear_effect_cache(app:AppHandle)->Result<(),String>{
  let dir=cache_dir(&app)?;if dir.exists(){fs::remove_dir_all(&dir).map_err(|e|e.to_string())?;fs::create_dir_all(&dir).map_err(|e|e.to_string())?;}Ok(())
}
