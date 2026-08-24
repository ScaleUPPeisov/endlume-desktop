use crate::{assets,model::QueueJob};
use serde_json::{json,Value};
use std::{fs,path::{Path,PathBuf}};
use tauri::{AppHandle,Manager};

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

pub fn write_value(app:&AppHandle,name:&str,v:&Value)->anyhow::Result<()>{
  let path=dir(app)?.join(name);
  let tmp=path.with_extension("tmp");
  fs::write(&tmp,serde_json::to_vec_pretty(v)?)?;
  if path.exists(){let _=fs::remove_file(&path);}
  fs::rename(tmp,path)?;
  Ok(())
}

fn migrate_item(app:&AppHandle,item:&mut Value,kind:&str)->bool{
  let Some(obj)=item.as_object_mut() else{return false};
  let source=obj.get("source").and_then(Value::as_str).unwrap_or("").to_string();
  if source.trim().is_empty(){return false}
  if Path::new(&source).is_file(){
    match assets::ensure_managed_asset(app,&source,kind){
      Ok(managed) if managed!=source=>{obj.insert("source".into(),json!(managed));obj.insert("cacheReady".into(),json!(false));obj.insert("cacheKey".into(),Value::Null);true},
      _=>false,
    }
  }else{
    let mut changed=false;
    if obj.get("enabled").and_then(Value::as_bool).unwrap_or(false){obj.insert("enabled".into(),json!(false));changed=true;}
    if obj.get("cacheReady").and_then(Value::as_bool).unwrap_or(false){obj.insert("cacheReady".into(),json!(false));changed=true;}
    if obj.get("cacheKey").map(|v|!v.is_null()).unwrap_or(false){obj.insert("cacheKey".into(),Value::Null);changed=true;}
    changed
  }
}

fn migrate_library(app:&AppHandle,v:&mut Value)->bool{
  let Some(obj)=v.as_object_mut() else{return false};
  let mut changed=false;
  if let Some(items)=obj.get_mut("effects").and_then(Value::as_array_mut){for item in items{changed|=migrate_item(app,item,"effects");}}
  if let Some(items)=obj.get_mut("subscribes").and_then(Value::as_array_mut){for item in items{changed|=migrate_item(app,item,"subscribe");}}
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
