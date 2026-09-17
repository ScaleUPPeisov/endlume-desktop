use serde::{Deserialize,Serialize};
use sha2::{Digest,Sha256};
use std::{fs,path::{Path,PathBuf},sync::{Arc,Mutex}};
use tauri::{AppHandle,Manager};
use tauri_plugin_updater::{Update,UpdaterExt};

#[derive(Debug,Clone,Serialize)]
#[serde(rename_all="camelCase")]
pub struct LocalUpdateInfo{
  supported:bool,
  available:bool,
  current:String,
  version:Option<String>,
  notes:Option<String>,
  date:Option<String>,
  reason:Option<String>,
}

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct LocalUpdateStatus{
  state:String,
  stage:Option<String>,
  progress:f64,
  message:Option<String>,
  log_path:Option<String>,
}

fn app_update_dir(app:&AppHandle)->Result<PathBuf,String>{
  let p=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("update-center");
  fs::create_dir_all(&p).map_err(|e|e.to_string())?;
  Ok(p)
}

fn state_path(app:&AppHandle)->Result<PathBuf,String>{Ok(app_update_dir(app)?.join("state.json"))}

fn write_state(path:&Path,status:&LocalUpdateStatus)->Result<(),String>{
  fs::write(path,serde_json::to_vec(status).map_err(|e|e.to_string())?).map_err(|e|e.to_string())
}

fn state(state:&str,stage:&str,progress:f64,message:Option<String>)->LocalUpdateStatus{
  LocalUpdateStatus{state:state.into(),stage:Some(stage.into()),progress,message,log_path:None}
}

fn sha256_hex(bytes:&[u8])->String{
  let digest=Sha256::digest(bytes);
  digest.iter().map(|b|format!("{b:02x}")).collect()
}

fn expected_sha256(update:&Update)->Option<String>{
  if let Some(v)=update.raw_json.get("sha256").and_then(|v|v.as_str()){
    return Some(v.trim().to_ascii_lowercase())
  }
  let wanted=update.download_url.as_str();
  update.raw_json.get("platforms")?.as_object()?.values().find_map(|platform|{
    let url=platform.get("url")?.as_str()?;
    if url==wanted{platform.get("sha256")?.as_str().map(|s|s.trim().to_ascii_lowercase())}else{None}
  })
}

async fn check(app:&AppHandle)->Result<Option<Update>,String>{
  app.updater().map_err(|e|format!("Windows updater init: {e}"))?
    .check().await.map_err(|e|format!("Windows updater check: {e}"))
}

#[tauri::command]
pub async fn local_update_check(app:AppHandle)->LocalUpdateInfo{
  let current=env!("CARGO_PKG_VERSION").to_string();
  match check(&app).await{
    Ok(Some(update))=>{
      let sha=expected_sha256(&update);
      LocalUpdateInfo{
        supported:true,
        available:true,
        current,
        version:Some(update.version.clone()),
        notes:update.body.clone(),
        date:update.date.map(|d|d.to_string()),
        reason:if sha.is_some(){None}else{Some("Update manifest не содержит обязательный SHA-256 для Windows package".into())},
      }
    },
    Ok(None)=>LocalUpdateInfo{supported:true,available:false,current,version:None,notes:None,date:None,reason:None},
    Err(e)=>LocalUpdateInfo{supported:true,available:false,current,version:None,notes:None,date:None,reason:Some(e)},
  }
}

#[tauri::command]
pub async fn local_update_start(app:AppHandle)->Result<LocalUpdateStatus,String>{
  let path=state_path(&app)?;
  let update=check(&app).await?.ok_or_else(||format!("Уже установлена актуальная версия {}",env!("CARGO_PKG_VERSION")))?.restart_after_install(true);
  let expected=expected_sha256(&update).ok_or("Windows update manifest не содержит SHA-256; установка заблокирована")?;
  if expected.len()!=64||!expected.chars().all(|c|c.is_ascii_hexdigit()){
    return Err("Windows update manifest содержит некорректный SHA-256".into())
  }

  let initial=state("downloading","Скачиваю подписанное обновление",5.0,Some(format!("ENDLUME {}",update.version)));
  write_state(&path,&initial)?;

  let progress=Arc::new(Mutex::new((0usize,None::<u64>)));
  let progress_cb=progress.clone();
  let progress_path=path.clone();
  let bytes=update.download(
    move |chunk,total|{
      if let Ok(mut p)=progress_cb.lock(){
        p.0=p.0.saturating_add(chunk);
        if total.is_some(){p.1=total}
        let pct=p.1.filter(|n|*n>0).map(|n|5.0+(p.0 as f64/n as f64*65.0).clamp(0.0,65.0)).unwrap_or(25.0);
        let _=write_state(&progress_path,&state("downloading","Скачиваю подписанное обновление",pct,None));
      }
    },
    ||{}
  ).await.map_err(|e|{
    let msg=format!("Проверка updater signature / загрузка Windows package: {e}");
    let _=write_state(&path,&state("failed","Обновление остановлено",0.0,Some(msg.clone())));
    msg
  })?;

  write_state(&path,&state("verifying","Проверяю SHA-256",75.0,None))?;
  let actual=sha256_hex(&bytes);
  if actual!=expected{
    let msg=format!("SHA-256 mismatch: expected {expected}, got {actual}");
    write_state(&path,&state("failed","Проверка SHA-256 не пройдена",0.0,Some(msg.clone())))?;
    return Err(msg)
  }

  write_state(&path,&state("installing","Подпись и SHA-256 проверены. Устанавливаю обновление",90.0,None))?;
  update.install(bytes).map_err(|e|{
    let msg=format!("Не удалось запустить Windows installer: {e}");
    let _=write_state(&path,&state("failed","Установка не запущена",0.0,Some(msg.clone())));
    msg
  })?;

  let done=state("success","Windows installer запущен",100.0,Some("ENDLUME будет перезапущен установщиком".into()));
  let _=write_state(&path,&done);
  Ok(done)
}

#[tauri::command]
pub fn local_update_status(app:AppHandle)->Result<LocalUpdateStatus,String>{
  let path=state_path(&app)?;
  if !path.is_file(){return Ok(LocalUpdateStatus{state:"idle".into(),stage:None,progress:0.0,message:None,log_path:None})}
  serde_json::from_slice::<LocalUpdateStatus>(&fs::read(path).map_err(|e|e.to_string())?).map_err(|e|e.to_string())
}

#[cfg(test)]
mod tests{
  use super::*;
  #[test]
  fn sha256_is_stable(){assert_eq!(sha256_hex(b"endlume"),"b6934e3ed44b11fd10f188267a51b2c1c0f3519f05374ac060732fa161508e19")}
}
