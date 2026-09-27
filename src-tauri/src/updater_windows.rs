use serde::{Deserialize,Serialize};
use sha2::{Digest,Sha256};
use std::{fs,path::{Path,PathBuf},sync::{Arc,Mutex},time::Instant};
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
  downloaded_bytes:Option<u64>,
  total_bytes:Option<u64>,
  bytes_per_second:Option<f64>,
  eta_seconds:Option<f64>,
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
  LocalUpdateStatus{state:state.into(),stage:Some(stage.into()),progress,message,log_path:None,downloaded_bytes:None,total_bytes:None,bytes_per_second:None,eta_seconds:None}
}

fn transfer_state(state_name:&str,stage:&str,progress:f64,message:Option<String>,downloaded:u64,total:Option<u64>,elapsed:f64)->LocalUpdateStatus{
  let speed=if elapsed>0.05{Some(downloaded as f64/elapsed)}else{None};
  let eta=match(total,speed){(Some(t),Some(v)) if v>1.0&&t>downloaded=>Some((t-downloaded)as f64/v),_=>None};
  LocalUpdateStatus{state:state_name.into(),stage:Some(stage.into()),progress,message,log_path:None,downloaded_bytes:Some(downloaded),total_bytes:total,bytes_per_second:speed,eta_seconds:eta}
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
  app.updater().map_err(|e|format!("ENDLUME updater init: {e}"))?
    .check().await.map_err(|e|format!("ENDLUME updater check: {e}"))
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
        reason:if sha.is_some(){None}else{Some("Update manifest не содержит обязательный SHA-256 для update package".into())},
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
  let expected=expected_sha256(&update).ok_or("Update manifest не содержит SHA-256; установка заблокирована")?;
  if expected.len()!=64||!expected.chars().all(|c|c.is_ascii_hexdigit()){
    return Err("Update manifest содержит некорректный SHA-256".into())
  }

  let initial=state("DOWNLOADING","Скачиваю подписанное обновление",5.0,Some(format!("ENDLUME {}",update.version)));
  write_state(&path,&initial)?;

  let progress=Arc::new(Mutex::new((0usize,None::<u64>)));
  let progress_cb=progress.clone();
  let progress_path=path.clone();
  let download_started=Instant::now();
  let bytes=update.download(
    move |chunk,total|{
      if let Ok(mut p)=progress_cb.lock(){
        p.0=p.0.saturating_add(chunk);
        if total.is_some(){p.1=total}
        let pct=p.1.filter(|n|*n>0).map(|n|5.0+(p.0 as f64/n as f64*65.0).clamp(0.0,65.0)).unwrap_or(25.0);
        let status=transfer_state("DOWNLOADING","Скачиваю подписанное обновление",pct,None,p.0 as u64,p.1,download_started.elapsed().as_secs_f64());
        let _=write_state(&progress_path,&status);
      }
    },
    ||{}
  ).await.map_err(|e|{
    let msg=format!("Проверка updater signature / загрузка package: {e}");
    let _=write_state(&path,&state("FAILED","Обновление остановлено",0.0,Some(msg.clone())));
    msg
  })?;

  let downloaded=bytes.len() as u64;
  let total=progress.lock().ok().and_then(|p|p.1).or(Some(downloaded));
  let elapsed=download_started.elapsed().as_secs_f64();
  write_state(&path,&transfer_state("VERIFYING","Проверяю SHA-256",75.0,None,downloaded,total,elapsed))?;
  let actual=sha256_hex(&bytes);
  if actual!=expected{
    let msg=format!("SHA-256 mismatch: expected {expected}, got {actual}");
    write_state(&path,&state("FAILED","Проверка SHA-256 не пройдена",0.0,Some("Файл обновления не прошёл проверку целостности.".into())))?;
    return Err(msg)
  }

  write_state(&path,&transfer_state("READY_TO_INSTALL","SHA-256 совпадает. Пакет готов к установке",86.0,None,downloaded,total,elapsed))?;
  write_state(&path,&transfer_state("INSTALLING","Подпись и SHA-256 проверены. Устанавливаю обновление",90.0,None,downloaded,total,elapsed))?;
  update.install(bytes).map_err(|e|{
    let msg=format!("Не удалось установить обновление: {e}");
    let _=write_state(&path,&state("FAILED","Установка не запущена",0.0,Some(msg.clone())));
    msg
  })?;

  let done=transfer_state("RESTART_REQUIRED","Обновление установлено",100.0,Some("ENDLUME будет перезапущен после установки".into()),downloaded,total,elapsed);
  let _=write_state(&path,&done);
  Ok(done)
}

#[tauri::command]
pub fn local_update_status(app:AppHandle)->Result<LocalUpdateStatus,String>{
  let path=state_path(&app)?;
  if !path.is_file(){return Ok(LocalUpdateStatus{state:"IDLE".into(),stage:None,progress:0.0,message:None,log_path:None,downloaded_bytes:None,total_bytes:None,bytes_per_second:None,eta_seconds:None})}
  serde_json::from_slice::<LocalUpdateStatus>(&fs::read(path).map_err(|e|e.to_string())?).map_err(|e|e.to_string())
}

#[cfg(test)]
mod tests{
  use super::*;
  #[test]
  fn sha256_is_stable(){assert_eq!(sha256_hex(b"endlume"),"0a5ca25411a68047ac7ea36cde07e9b37a6b601d9bdfcd8eb8234ae89d1db760")}
}
