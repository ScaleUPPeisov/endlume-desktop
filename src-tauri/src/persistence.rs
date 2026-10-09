use crate::model::QueueJob;
use serde_json::{json,Value};
use std::{fs,path::PathBuf};
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
  // Windows does not reliably replace an existing destination with rename().
  // Remove the old tiny JSON only after the new temp file is fully written.
  if path.exists(){let _=fs::remove_file(&path);}
  fs::rename(tmp,path)?;
  Ok(())
}

#[tauri::command]
pub fn load_library(app:AppHandle)->Value{
  let v=read_value(&app,"library.json");
  if v.is_object() && !v.as_object().unwrap().is_empty(){v}else{json!({"effects":[],"subscribes":[],"ambient":null})}
}

#[tauri::command]
pub fn save_library(app:AppHandle,payload:Value)->Result<(),String>{
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
