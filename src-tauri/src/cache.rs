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
pub(crate) fn despill_type(hex:&str)->&'static str{
  let raw=hex.trim().trim_start_matches('#');
  if raw.len()==6{if let Ok(v)=u32::from_str_radix(raw,16){let g=(v>>8)&255;let b=v&255;if b>g{return "blue"}}}
  "green"
}

pub(crate) fn is_round_equalizer_859(e:&EffectPreset)->bool{
  if e.mode!="chromakey"{return false}
  let name=e.name.trim().to_lowercase();
  e.id==ROUND_EQUALIZER_859_ID || name=="эквалайзер круглый"
}

pub(crate) fn chromakey_params_859(e:&EffectPreset)->(f64,f64){
  // Legacy alpha.8 presets used the exact 0.60 / 0.184 pair. On the 10.0.10
  // fused-direct fast path those values are applied to the RAW overlay and can
  // key away almost the whole ordinary Effect. Treat only that exact legacy
  // signature as a migration sentinel; all real user-selected values survive.
  if is_round_equalizer_859(e){
    (ROUND_EQUALIZER_859_SIMILARITY,ROUND_EQUALIZER_859_BLEND)
  }else if (e.similarity-0.60).abs()<0.000_001 && (e.blend-0.184).abs()<0.000_001{
    (0.10,0.06)
  }else{
    (e.similarity.clamp(0.001,0.60),e.blend.clamp(0.001,0.35))
  }
}

pub(crate) fn subscribe_chromakey_params_1011(e:&EffectPreset)->(f64,f64){
  // Real 10.0.11 user preset diagnostic: the legacy Subscribe UI max pair
  // 0.60 / 0.35 leaves essentially no opaque pixels (alpha >= 128 = 0).
  // Migrate ONLY this exact Subscribe signature. Ordinary Effects and the
  // protected Round Equalizer continue through chromakey_params_859 unchanged.
  if e.mode=="chromakey" && (e.similarity-0.60).abs()<0.000_001 && (e.blend-0.35).abs()<0.000_001{
    (0.10,0.06)
  }else{
    chromakey_params_859(e)
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
  let eq859=if is_round_equalizer_859(e){"|round-equalizer-859-s018-b003-name-safe"}else{""};
  h.update(format!("aspect-safe-v6-motion|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}{}",e.source,size,modified,fps,e.mode,e.key_color,e.similarity,e.blend,e.luma_threshold,e.luma_tolerance,e.saturation,e.despill,eq859));
  hex::encode(h.finalize())[..24].to_string()
}


fn strict_cache_dir_856(app:&AppHandle)->Result<PathBuf,String>{
  let p=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("strict-effects-856");
  fs::create_dir_all(&p).map_err(|e|format!("Не удалось создать Strict Effects cache: {e}"))?;Ok(p)
}
fn strict_fingerprint_856(e:&EffectPreset,fps:u32,width:u32,height:u32)->String{
  let meta=fs::metadata(&e.source).ok();let modified=meta.as_ref().and_then(|m|m.modified().ok()).and_then(|t|t.duration_since(UNIX_EPOCH).ok()).map(|d|d.as_secs()).unwrap_or(0);let size=meta.as_ref().map(|m|m.len()).unwrap_or(0);
  let (similarity,blend)=chromakey_params_859(e);let mut h=Sha256::new();h.update(format!("strict-860|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",e.source,size,modified,fps,width,height,e.mode,e.key_color,similarity,blend,e.luma_threshold,e.luma_tolerance,e.scale,e.fullscreen,e.saturation));hex::encode(h.finalize())[..24].to_string()
}
fn clear_stale_strict_lock_1002(lock:&Path){
  let stale=fs::metadata(lock).ok()
    .and_then(|m|m.modified().ok())
    .and_then(|t|t.elapsed().ok())
    .map(|age|age.as_secs()>=120)
    .unwrap_or(false);
  if stale{let _=fs::remove_file(lock);}
}

pub async fn prepare_strict_856(app:&AppHandle,e:&EffectPreset,fps:u32,width:u32,height:u32)->Result<EffectPreset,String>{
  if !e.enabled||e.source.trim().is_empty(){return Ok(e.clone())}
  if !Path::new(&e.source).is_file(){return Err(format!("Не найден файл эффекта: {}",e.source))}
  let key=strict_fingerprint_856(e,fps,width,height);let path=strict_cache_dir_856(app)?.join(format!("{key}.mov"));let lock=path.with_extension("lock");
  clear_stale_strict_lock_1002(&lock);
  if !path.exists(){
    match std::fs::OpenOptions::new().write(true).create_new(true).open(&lock){
      Ok(_guard)=>{
        let target=((width as f64)*e.scale.clamp(0.05,1.5)).round().max(2.0) as u32;let target=if target%2==0{target}else{target+1};
        let scale=if e.fullscreen{format!("scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0")}else{format!("scale={target}:-2:flags=lanczos")};
        let (similarity,blend)=chromakey_params_859(e);
        let vf=match e.mode.as_str(){
          "luma"=>format!("fps={fps},format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08,{scale},format=argb",e.luma_threshold,e.luma_tolerance),
          "screen"|"screen-cache"=>format!("fps={fps},format=rgb24,{scale}"),
          _=>format!("fps={fps},format=rgba,colorkey={}:{}:{},{scale},format=argb",color(&e.key_color),similarity,blend)
        };
        let pix=if e.mode=="screen"||e.mode=="screen-cache"{"rgb24"}else{"argb"};let tmp=path.with_extension(format!("{}.tmp.mov",uuid::Uuid::new_v4()));
        let args=vec!["-hide_banner","-loglevel","error","-i",e.source.as_str(),"-vf",vf.as_str(),"-an","-c:v","qtrle","-pix_fmt",pix,"-y",tmp.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();
        let out=app.shell().sidecar("ffmpeg").map_err(|x|format!("Не найден FFmpeg для Strict Effects: {x}"))?.args(args).output().await.map_err(|x|format!("Не удалось запустить Strict Effects cache: {x}"))?;
        if !out.status.success(){let _=fs::remove_file(&tmp);let _=fs::remove_file(&lock);return Err(format!("Strict Effects cache '{}': {}",e.name,String::from_utf8_lossy(&out.stderr).trim()))}
        if path.exists(){let _=fs::remove_file(&path);}fs::rename(&tmp,&path).map_err(|x|format!("Strict Effects cache finalize: {x}"))?;let _=fs::remove_file(&lock);
      },
      Err(_)=>{
        for _ in 0..400{if path.exists(){break}tokio::time::sleep(std::time::Duration::from_millis(100)).await;}
        if !path.exists(){let _=fs::remove_file(&lock);return Err(format!("Strict Effects cache '{}' не успел подготовиться",e.name))}
      }
    }
  }
  let mut prepared=e.clone();prepared.source=path.to_string_lossy().into_owned();prepared.cache_key=Some(key);prepared.cache_ready=Some(true);prepared.mode=if e.mode=="screen"||e.mode=="screen-cache"{"strict-screen-cache".into()}else{"strict-prealpha".into()};Ok(prepared)
}

pub fn start_strict_prewarm_856(_app:AppHandle){
  // 10.0.8: smart static renders fuse keying directly into the persistent HEVC
  // visual master. Pre-rendering a full-duration qtrle copy duplicated the same
  // chroma/luma work and cost the measured cold path ~6-15 seconds.
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
    preview_frame_time:0.0,start_sec:0.0,end_sec:None,cache_key:None,cache_ready:None,usage_mode:None,interval_sec:None,usage_duration_sec:None,target:None,offset_x:None,offset_y:None,opacity:None
  }}

  #[test]
  fn subscribe_1011_migrates_only_destructive_max_pair(){
    let mut sub=preset("subscribe-real","ПОДПИСКА");
    sub.similarity=0.60;sub.blend=0.35;
    assert_eq!(subscribe_chromakey_params_1011(&sub),(0.10,0.06));
    sub.blend=0.34;
    assert_eq!(subscribe_chromakey_params_1011(&sub),(0.60,0.34));
    let eq=preset(ROUND_EQUALIZER_859_ID,"эквалайзер круглый");
    assert_eq!(subscribe_chromakey_params_1011(&eq),(0.18,0.03));
  }

  #[test]
  fn round_equalizer_859_only_gets_protected_key(){
    let eq=preset(ROUND_EQUALIZER_859_ID,"эквалайзер круглый");
    assert_eq!(chromakey_params_859(&eq),(0.18,0.03));
    let dust=preset("9951d1c3-5ff6-4a37-891f-1c323889a663","пыль и царапины 80-х");
    assert_eq!(chromakey_params_859(&dust),(0.10,0.06));
    let mut custom=dust.clone();custom.similarity=0.31;custom.blend=0.09;
    assert_eq!(chromakey_params_859(&custom),(0.31,0.09));
  }
}
