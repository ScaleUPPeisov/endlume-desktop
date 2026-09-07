use crate::model::EffectPreset;
use serde_json::json;
use sha2::{Digest,Sha256};
use std::{fs,path::{Path,PathBuf},time::UNIX_EPOCH};
use tauri::{AppHandle,Emitter,Manager};
use tauri_plugin_shell::ShellExt;

const ROUND_EQUALIZER_859_ID:&str="825dd7a4-f0cf-4032-a3c9-64290cb5756d";
const ROUND_EQUALIZER_859_SIMILARITY:f64=0.18;
const ROUND_EQUALIZER_859_BLEND:f64=0.03;

fn color(hex:&str)->String{format!("0x{}",hex.trim().trim_start_matches('#').trim_start_matches("0x"))}
fn despill_type(hex:&str)->&'static str{
  let raw=hex.trim().trim_start_matches('#');
  if raw.len()==6{if let Ok(v)=u32::from_str_radix(raw,16){let g=(v>>8)&255;let b=v&255;if b>g{return "blue"}}}
  "green"
}

fn chromakey_params_859(e:&EffectPreset)->(f64,f64){
  // 8.59 is intentionally scoped to this one existing preset only. The legacy
  // 0.60 / 0.184 values key away the equalizer itself, leaving it mostly
  // semi-transparent. Every other Effect keeps its user-selected key values.
  if e.id==ROUND_EQUALIZER_859_ID && e.mode=="chromakey"{
    (ROUND_EQUALIZER_859_SIMILARITY,ROUND_EQUALIZER_859_BLEND)
  }else{
    (e.similarity.clamp(0.001,0.60),e.blend.clamp(0.001,0.35))
  }
}

fn cache_dir(app:&AppHandle)->Result<PathBuf,String>{
  // v4 cache contains only keyed pixels at the ORIGINAL source geometry.
  // Position/scale/fullscreen are applied later by the compositor, so resizing an
  // effect never stretches the source and never forces a new chromakey encode.
  let p=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("effects-v4-aspect-safe");
  fs::create_dir_all(&p).map_err(|e|format!("Не удалось создать кэш Effects: {e}"))?;
  Ok(p)
}

fn fingerprint(e:&EffectPreset,fps:u32)->String{
  let meta=fs::metadata(&e.source).ok();
  let modified=meta.as_ref().and_then(|m|m.modified().ok()).and_then(|t|t.duration_since(UNIX_EPOCH).ok()).map(|d|d.as_secs()).unwrap_or(0);
  let size=meta.as_ref().map(|m|m.len()).unwrap_or(0);
  let mut h=Sha256::new();
  // Geometry is deliberately absent from the key: x/y/scale/fullscreen do not
  // change source pixels and therefore must not invalidate the chroma cache.
  let eq859=if e.id==ROUND_EQUALIZER_859_ID && e.mode=="chromakey"{"|round-equalizer-859-s018-b003"}else{""};
  h.update(format!("aspect-safe-v6-motion|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}{}",e.source,size,modified,fps,e.mode,e.key_color,e.similarity,e.blend,e.luma_threshold,e.luma_tolerance,e.saturation,e.despill,eq859));
  hex::encode(h.finalize())[..24].to_string()
}

pub async fn prepare(app:&AppHandle,e:&EffectPreset,fps:u32)->Result<EffectPreset,String>{
  if !e.enabled||e.source.trim().is_empty(){return Ok(e.clone())}
  if !Path::new(&e.source).is_file(){return Err(format!("Не найден файл эффекта: {}",e.source))}
  let key=fingerprint(e,fps);let path=cache_dir(app)?.join(format!("{}.mov",key));
  if !path.exists(){
    let (similarity,blend)=chromakey_params_859(e);
    let motion=if fps>=50{format!("minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")}else{format!("fps={fps}")};
    let vf=match e.mode.as_str(){
      "luma"=>format!("{motion},format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08,format=argb",e.luma_threshold,e.luma_tolerance),
      "screen"=>format!("{motion},format=rgb24"),
      _=>format!("{motion},format=rgba,colorkey={}:{}:{},despill=type={}:mix={}:expand=0.20,format=argb",color(&e.key_color),similarity,blend,despill_type(&e.key_color),e.despill.clamp(0.0,1.0))
    };
    let pix=if e.mode=="screen"{"rgb24"}else{"argb"};
    let args=vec!["-hide_banner","-loglevel","error","-i",e.source.as_str(),"-vf",vf.as_str(),"-an","-c:v","qtrle","-pix_fmt",pix,"-y",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();
    let out=app.shell().sidecar("ffmpeg").map_err(|x|format!("Не найден встроенный FFmpeg: {x}"))?.args(args).output().await.map_err(|x|format!("Не удалось запустить FFmpeg для Effects: {x}"))?;
    if !out.status.success(){return Err(format!("Не удалось подготовить кэш '{}': {}",e.name,String::from_utf8_lossy(&out.stderr).trim()))}
  }
  let mut prepared=e.clone();prepared.source=path.to_string_lossy().into_owned();prepared.cache_key=Some(key.clone());prepared.cache_ready=Some(true);
  prepared.mode=if e.mode=="screen"{"screen-cache".into()}else{"prealpha".into()};
  // IMPORTANT: keep the original user scale. The render compositor applies it
  // relative to the output canvas width and uses -2 height to preserve aspect.
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

#[cfg(test)]
mod tests{
  use super::*;
  use crate::model::EffectPreset;

  fn preset(id:&str,name:&str)->EffectPreset{EffectPreset{
    id:id.into(),name:name.into(),source:"/tmp/fx.mp4".into(),enabled:true,mode:"chromakey".into(),key_color:"#0aa843".into(),
    similarity:0.6,blend:0.184,despill:0.35,luma_threshold:0.03,luma_tolerance:0.08,saturation:1.0,x:0.5,y:0.5,scale:1.0,fullscreen:false,
    preview_frame_time:0.0,start_sec:0.0,end_sec:None,cache_key:None,cache_ready:None
  }}

  #[test]
  fn round_equalizer_859_only_gets_protected_key(){
    let eq=preset(ROUND_EQUALIZER_859_ID,"эквалайзер круглый");
    assert_eq!(chromakey_params_859(&eq),(0.18,0.03));
    let dust=preset("9951d1c3-5ff6-4a37-891f-1c323889a663","пыль и царапины 80-х");
    assert_eq!(chromakey_params_859(&dust),(0.6,0.184));
  }
}
