use crate::{assets,model::QueueJob};
use serde_json::{json,Value};
use std::{collections::HashMap,fs,path::{Path,PathBuf}};
use tauri::{AppHandle,Manager};
use uuid::Uuid;

fn dir(app:&AppHandle)->anyhow::Result<PathBuf>{
  let p=app.path().app_data_dir()?;
  fs::create_dir_all(&p)?;
  Ok(p)
}

pub fn read_value(app:&AppHandle,name:&str)->Value{
  dir(app).ok()
    .and_then(|d|fs::read(d.join(name)).ok())
    .and_then(|bytes|serde_json::from_slice(&bytes).ok())
    .unwrap_or_else(||json!({}))
}

pub fn write_value(app:&AppHandle,name:&str,v:&Value)->anyhow::Result<()> {
  let path=dir(app)?.join(name);
  let tmp=path.with_extension("tmp");
  fs::write(&tmp,serde_json::to_vec_pretty(v)?)?;
  if path.exists(){let _=fs::remove_file(&path);}
  fs::rename(tmp,path)?;
  Ok(())
}

fn migrate_item(app:&AppHandle,item:&mut Value,kind:&str)->bool{
  let Some(obj)=item.as_object_mut() else{return false};
  let mut changed=false;
  let source=obj.get("source").and_then(Value::as_str).unwrap_or("").to_string();
  if !source.trim().is_empty(){
    if Path::new(&source).is_file(){
      if let Ok(managed)=assets::ensure_managed_asset(app,&source,kind){
        if managed!=source{obj.insert("source".into(),json!(managed));obj.insert("cacheReady".into(),json!(false));obj.insert("cacheKey".into(),Value::Null);changed=true;}
      }
    }else{
      obj.insert("source".into(),json!(""));
      obj.insert("enabled".into(),json!(false));
      obj.insert("cacheReady".into(),json!(false));
      obj.insert("cacheKey".into(),Value::Null);
      changed=true;
    }
  }
  // ENDLUME 10.0.6 could leave an explicit OFF usage mode behind while a
  // quick UI toggle set enabled=true. The renderer correctly treats usageMode=off
  // as disabled, so normalize only this contradictory legacy state.
  let enabled=obj.get("enabled").and_then(Value::as_bool).unwrap_or(false);
  let usage=obj.get("usageMode").and_then(Value::as_str).unwrap_or("");
  if enabled&&usage=="off"{
    obj.insert("usageMode".into(),json!(if kind=="subscribe"{"interval"}else{"always"}));
    changed=true;
  }

  // alpha.8.18 could leave chromakey at extreme 0.9–1.0 values while the old
  // WebGL preview also boosted saturation. Those values erase most of the overlay.
  // Bring only obviously broken legacy presets back to conservative defaults.
  // IMPORTANT: despill=0 is a valid explicit production setting (e.g. neutral smoke)
  // and must survive save/reload unchanged.
  if obj.get("mode").and_then(Value::as_str)==Some("chromakey"){
    let sim=obj.get("similarity").and_then(Value::as_f64).unwrap_or(0.10);
    let blend=obj.get("blend").and_then(Value::as_f64).unwrap_or(0.06);
    if sim>0.60{obj.insert("similarity".into(),json!(0.10));changed=true;}
    if blend>0.35{obj.insert("blend".into(),json!(0.06));changed=true;}
    if obj.get("saturation").and_then(Value::as_f64).unwrap_or(1.0)!=1.0{obj.insert("saturation".into(),json!(1.0));changed=true;}
    if !obj.contains_key("despill"){obj.insert("despill".into(),json!(0.35));changed=true;}
    if changed{obj.insert("cacheReady".into(),json!(false));obj.insert("cacheKey".into(),Value::Null);}
  }
  changed
}

fn normalize_effect_identities(items:&mut Vec<Value>)->bool{
  let old=std::mem::take(items);
  let mut out=Vec::with_capacity(old.len());
  let mut seen:HashMap<String,Value>=HashMap::new();
  let mut changed=false;
  for mut item in old{
    if !item.is_object(){out.push(item);continue}
    let mut id=item.get("id").and_then(Value::as_str).unwrap_or("").trim().to_string();
    if id.is_empty(){
      id=Uuid::new_v4().to_string();
      if let Some(obj)=item.as_object_mut(){obj.insert("id".into(),json!(id.clone()));}
      changed=true;
    }
    if let Some(first)=seen.get(&id){
      if first==&item{
        // Remove only a truly identical persisted record. Reusing the same source
        // asset with different geometry/chroma/usage settings is a valid preset and
        // must never be silently deleted.
        changed=true;
        continue
      }
      // One stable ID may not address two different preset definitions. Preserve
      // both records and split the conflicting identity once; the new UUID is then
      // persisted so selection remains stable across subsequent launches.
      id=Uuid::new_v4().to_string();
      if let Some(obj)=item.as_object_mut(){obj.insert("id".into(),json!(id.clone()));}
      changed=true;
    }
    seen.insert(id,item.clone());
    out.push(item);
  }
  *items=out;
  changed
}

fn migrate_library(app:&AppHandle,v:&mut Value)->bool{
  let Some(obj)=v.as_object_mut() else{return false};
  let mut changed=false;
  if let Some(items)=obj.get_mut("effects").and_then(Value::as_array_mut){
    for item in items.iter_mut(){changed|=migrate_item(app,item,"effects");}
    changed|=normalize_effect_identities(items);
  }
  if let Some(items)=obj.get_mut("subscribes").and_then(Value::as_array_mut){
    for item in items.iter_mut(){changed|=migrate_item(app,item,"subscribe");}
    changed|=normalize_effect_identities(items);
  }
  if let Some(ambient)=obj.get("ambient").and_then(Value::as_str).map(str::to_string){
    if !ambient.trim().is_empty(){
      if Path::new(&ambient).is_file(){
        if let Ok(managed)=assets::ensure_managed_asset(app,&ambient,"ambient"){
          if managed!=ambient{obj.insert("ambient".into(),json!(managed));changed=true;}
        }
      }else{obj.insert("ambient".into(),Value::Null);changed=true;}
    }
  }
  changed
}

#[tauri::command]
pub fn load_library(app:AppHandle)->Value{
  let mut v=read_value(&app,"library.json");
  if !v.is_object()||v.as_object().map(|x|x.is_empty()).unwrap_or(true){return json!({"effects":[],"subscribes":[],"ambient":null})}
  if migrate_library(&app,&mut v){let _=write_value(&app,"library.json",&v);}
  v
}

#[tauri::command]
pub fn save_library(app:AppHandle,mut payload:Value)->Result<(),String>{
  let _=migrate_library(&app,&mut payload);
  write_value(&app,"library.json",&payload).map_err(|e|e.to_string())
}

#[tauri::command]
pub fn load_recovery(app:AppHandle)->Value{read_value(&app,"recovery.json")}

#[tauri::command]
pub fn dismiss_recovery(app:AppHandle)->Result<(),String>{
  write_value(&app,"recovery.json",&json!({"interrupted":false})).map_err(|e|e.to_string())
}

pub fn save_queue_state(app:&AppHandle,active:Option<&QueueJob>,pending:&[QueueJob])->anyhow::Result<()> {
  write_value(app,"queue.json",&json!({"active":active,"pending":pending,"interrupted":false,"updatedAt":chrono::Utc::now()}))
}

pub fn clear_queue_state(app:&AppHandle)->anyhow::Result<()> {
  write_value(app,"queue.json",&json!({"active":null,"pending":[],"interrupted":false,"updatedAt":chrono::Utc::now()}))
}

pub fn mark_session_open(app:&AppHandle)->anyhow::Result<()> {
  let old=read_value(app,"session.json");
  let crashed=old.get("open").and_then(Value::as_bool).unwrap_or(false);
  if crashed{
    let mut r=read_value(app,"queue.json");
    let has_active=!r.get("active").map(Value::is_null).unwrap_or(true);
    let has_pending=r.get("pending").and_then(Value::as_array).map(|x|!x.is_empty()).unwrap_or(false);
    if has_active||has_pending{
      r["interrupted"]=json!(true);
      r["detectedAt"]=json!(chrono::Utc::now());
      write_value(app,"recovery.json",&r)?;
    }
  }
  write_value(app,"session.json",&json!({"open":true,"started":chrono::Utc::now()}))
}

pub fn mark_session_closed(app:&AppHandle)->anyhow::Result<()> {
  write_value(app,"session.json",&json!({"open":false,"closed":chrono::Utc::now()}))
}

#[cfg(test)]
mod tests{
  use super::normalize_effect_identities;
  use serde_json::json;

  #[test]
  fn fully_identical_duplicate_record_is_removed(){
    let preset=json!({"id":"same","source":"/tmp/effect.mp4","name":"A","scale":0.5,"similarity":0.1});
    let mut items=vec![preset.clone(),preset];
    assert!(normalize_effect_identities(&mut items));
    assert_eq!(items.len(),1);
    assert_eq!(items[0]["id"],"same");
  }

  #[test]
  fn same_asset_with_different_settings_is_preserved_with_new_id(){
    let mut items=vec![
      json!({"id":"collision","source":"/tmp/effect.mp4","name":"A","scale":0.5}),
      json!({"id":"collision","source":"/tmp/effect.mp4","name":"B","scale":0.9})
    ];
    assert!(normalize_effect_identities(&mut items));
    assert_eq!(items.len(),2);
    assert_eq!(items[0]["id"],"collision");
    assert_ne!(items[1]["id"],"collision");
    assert_ne!(items[0]["id"],items[1]["id"]);
    assert_eq!(items[1]["scale"],0.9);
  }

  #[test]
  fn distinct_assets_never_keep_the_same_id(){
    let mut items=vec![
      json!({"id":"collision","source":"/tmp/a.mp4","name":"A"}),
      json!({"id":"collision","source":"/tmp/b.mp4","name":"B"})
    ];
    assert!(normalize_effect_identities(&mut items));
    assert_eq!(items.len(),2);
    assert_eq!(items[0]["id"],"collision");
    assert_ne!(items[1]["id"],"collision");
    assert_ne!(items[0]["id"],items[1]["id"]);
  }
}
