use crate::{assets,model::QueueJob};
use serde_json::{json,Map,Value};
use std::{collections::HashMap,fs,path::{Path,PathBuf}};
use tauri::{AppHandle,Manager};
use uuid::Uuid;

fn dir(app:&AppHandle)->anyhow::Result<PathBuf>{
  let p=app.path().app_data_dir()?;
  fs::create_dir_all(&p)?;
  Ok(p)
}

pub fn read_value(app:&AppHandle,name:&str)->Value{
  #[cfg(feature="e2e-render")]
  if name=="library.json"{
    if let Ok(path)=std::env::var("ENDLUME_E2E_LIBRARY_PATH"){
      if let Ok(bytes)=fs::read(path){
        if let Ok(value)=serde_json::from_slice(&bytes){return value}
      }
    }
  }
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

fn set_json_field(obj:&mut Map<String,Value>,key:&str,value:Value)->bool{
  if obj.get(key)==Some(&value){return false}
  obj.insert(key.to_string(),value);true
}

fn mark_asset_ready(obj:&mut Map<String,Value>)->bool{
  let mut changed=set_json_field(obj,"assetState",json!("ready"));
  if obj.remove("assetError").is_some(){changed=true;}
  changed
}

fn mark_asset_repair_required(obj:&mut Map<String,Value>,message:String)->bool{
  let mut changed=false;
  changed|=set_json_field(obj,"assetState",json!("repair-required"));
  changed|=set_json_field(obj,"assetError",json!(message));
  changed|=set_json_field(obj,"cacheReady",json!(false));
  changed|=set_json_field(obj,"cacheKey",Value::Null);
  changed
}

fn migrate_item(app:&AppHandle,item:&mut Value,kind:&str)->bool{
  let Some(obj)=item.as_object_mut() else{return false};
  let mut changed=false;
  let source=obj.get("source").and_then(Value::as_str).unwrap_or("").to_string();

  if source.trim().is_empty(){
    changed|=mark_asset_repair_required(obj,"Источник файла не сохранён. Выберите исходный файл этого preset заново; ENDLUME не будет подставлять другой эффект.".into());
  }else if Path::new(&source).is_file(){
    match assets::ensure_managed_asset(app,&source,kind){
      Ok(managed)=>{
        if managed!=source{
          obj.insert("source".into(),json!(managed));
          obj.insert("cacheReady".into(),json!(false));
          obj.insert("cacheKey".into(),Value::Null);
          changed=true;
        }
        changed|=mark_asset_ready(obj);
      }
      Err(reason)=>{
        changed|=mark_asset_repair_required(obj,format!("Файл preset существует, но ENDLUME не смог сохранить его в managed library: {source}. {reason}"));
      }
    }
  }else{
    match assets::repair_missing_managed_asset(app,&source,kind){
      Ok(Some(repaired))=>{
        match assets::ensure_managed_asset(app,&repaired,kind){
          Ok(managed)=>{
            if obj.get("source").and_then(Value::as_str)!=Some(managed.as_str()){
              obj.insert("source".into(),json!(managed));
              changed=true;
            }
            changed|=set_json_field(obj,"cacheReady",json!(false));
            changed|=set_json_field(obj,"cacheKey",Value::Null);
            changed|=mark_asset_ready(obj);
          }
          Err(reason)=>{
            changed|=mark_asset_repair_required(obj,format!("ENDLUME нашёл точный managed asset для stale path '{source}', но не смог импортировать его в текущую managed library: {repaired}. {reason}"));
          }
        }
      }
      Ok(None)=>{
        changed|=mark_asset_repair_required(obj,format!("Файл preset не найден: {source}. ENDLUME сохранил identity и не будет скрывать или заменять этот эффект. Требуется восстановить источник."));
      }
      Err(reason)=>{
        changed|=mark_asset_repair_required(obj,format!("Файл preset не найден: {source}. {reason}"));
      }
    }
  }

  let enabled=obj.get("enabled").and_then(Value::as_bool).unwrap_or(false);
  let usage=obj.get("usageMode").and_then(Value::as_str).unwrap_or("");
  if enabled&&usage=="off"{
    obj.insert("usageMode".into(),json!(if kind=="subscribe"{"interval"}else{"always"}));
    changed=true;
  }
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
  let mut changed=false;

  for mut item in old{
    if !item.is_object(){out.push(item);continue}
    let id=item.get("id").and_then(Value::as_str).unwrap_or("").trim().to_string();
    if id.is_empty(){
      if let Some(obj)=item.as_object_mut(){obj.insert("id".into(),json!(Uuid::new_v4().to_string()));}
      changed=true;
    }
    if out.iter().any(|existing|existing==&item){changed=true;continue}
    out.push(item);
  }

  let mut counts=HashMap::<String,usize>::new();
  for item in &out{
    if let Some(id)=item.get("id").and_then(Value::as_str).map(str::trim).filter(|id|!id.is_empty()){
      *counts.entry(id.to_string()).or_insert(0)+=1;
    }
  }
  for item in out.iter_mut(){
    let id=item.get("id").and_then(Value::as_str).unwrap_or("").trim().to_string();
    if counts.get(&id).copied().unwrap_or(0)>1{
      if let Some(obj)=item.as_object_mut(){obj.insert("id".into(),json!(Uuid::new_v4().to_string()));}
      changed=true;
    }
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
  fn same_asset_with_different_settings_retires_ambiguous_id_for_all_presets(){
    let mut items=vec![
      json!({"id":"collision","source":"/tmp/effect.mp4","name":"A","scale":0.5}),
      json!({"id":"collision","source":"/tmp/effect.mp4","name":"B","scale":0.9})
    ];
    assert!(normalize_effect_identities(&mut items));
    assert_eq!(items.len(),2);
    assert_ne!(items[0]["id"],"collision");
    assert_ne!(items[1]["id"],"collision");
    assert_ne!(items[0]["id"],items[1]["id"]);
    assert_eq!(items[1]["scale"],0.9);
  }

  #[test]
  fn distinct_assets_retire_ambiguous_id_for_all_presets(){
    let mut items=vec![
      json!({"id":"collision","source":"/tmp/a.mp4","name":"A"}),
      json!({"id":"collision","source":"/tmp/b.mp4","name":"B"})
    ];
    assert!(normalize_effect_identities(&mut items));
    assert_eq!(items.len(),2);
    assert_ne!(items[0]["id"],"collision");
    assert_ne!(items[1]["id"],"collision");
    assert_ne!(items[0]["id"],items[1]["id"]);
  }
}
