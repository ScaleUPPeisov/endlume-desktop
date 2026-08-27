use serde::Serialize;
use std::{fs::{self,File,OpenOptions},io::Read,path::PathBuf,process::{Command,Stdio}};
#[cfg(unix)] use std::os::unix::fs::PermissionsExt;
use tauri::{AppHandle,Manager};

const REPO:&str="ScaleUPPeisov/endlume-desktop";

#[derive(Serialize)]
#[serde(rename_all="camelCase")]
pub struct UpdateCheck{pub supported:bool,pub available:bool,pub current:String,pub version:String,pub message:Option<String>}
#[derive(Serialize)]
#[serde(rename_all="camelCase")]
pub struct UpdateStart{pub pid:u32,pub version:String,pub log_path:String}
#[derive(Serialize)]
#[serde(rename_all="camelCase")]
pub struct UpdateStatus{pub running:bool,pub done:bool,pub failed:bool,pub progress:f64,pub stage:String,pub error:Option<String>}

fn gh_path()->Option<PathBuf>{["/opt/homebrew/bin/gh","/usr/local/bin/gh","/usr/bin/gh"].into_iter().map(PathBuf::from).find(|p|p.is_file())}
fn remote_version()->Result<String,String>{
  let gh=gh_path().ok_or("GitHub CLI не найден. Установи обновление один раз через установщик ENDLUME.")?;
  let endpoint=format!("/repos/{REPO}/contents/package.json?ref=release");
  let out=Command::new(gh).args(["api","-H","Accept: application/vnd.github.raw+json",endpoint.as_str()]).output().map_err(|e|e.to_string())?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
  let v:serde_json::Value=serde_json::from_slice(&out.stdout).map_err(|e|e.to_string())?;
  v.get("version").and_then(|x|x.as_str()).map(str::to_string).ok_or("В package.json нет version".into())
}
fn builder_name(version:&str)->Result<String,String>{
  let n=version.split("alpha.8.").nth(1).and_then(|x|x.split(|c:char|!c.is_ascii_digit()).next()).filter(|x|!x.is_empty()).ok_or("Не удалось определить номер alpha")?;
  Ok(format!("BUILD_ENDLUME_8{n}_LOCAL.command"))
}
fn stage_progress(stage:&str)->f64{stage.split('/').next().and_then(|x|x.trim().parse::<f64>().ok()).map(|x|(x*10.0).clamp(1.0,99.0)).unwrap_or(5.0)}

#[tauri::command]
pub async fn local_update_check()->Result<UpdateCheck,String>{
  #[cfg(not(target_os="macos"))]{return Ok(UpdateCheck{supported:false,available:false,current:env!("CARGO_PKG_VERSION").into(),version:env!("CARGO_PKG_VERSION").into(),message:Some("Фоновый локальный updater сейчас включён для macOS".into())})}
  #[cfg(target_os="macos")]{
    let current=env!("CARGO_PKG_VERSION").to_string();
    match remote_version(){Ok(version)=>Ok(UpdateCheck{supported:true,available:version!=current,current,version,message:None}),Err(e)=>Ok(UpdateCheck{supported:false,available:false,current:current.clone(),version:current,message:Some(e)})}
  }
}

#[tauri::command]
pub fn local_update_install(app:AppHandle,version:String)->Result<UpdateStart,String>{
  let gh=gh_path().ok_or("GitHub CLI не найден")?;let builder=builder_name(&version)?;
  let dir=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("background-updater");fs::create_dir_all(&dir).map_err(|e|e.to_string())?;
  let script=dir.join(&builder);let endpoint=format!("/repos/{REPO}/contents/{builder}?ref=release");
  let out=Command::new(gh).args(["api","-H","Accept: application/vnd.github.raw+json",endpoint.as_str()]).output().map_err(|e|e.to_string())?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
  fs::write(&script,&out.stdout).map_err(|e|e.to_string())?;
  #[cfg(unix)]{let mut perm=fs::metadata(&script).map_err(|e|e.to_string())?.permissions();perm.set_mode(0o755);fs::set_permissions(&script,perm).map_err(|e|e.to_string())?;}
  let log=dir.join("ENDLUME-update.log");let status=dir.join("exit-code.txt");let stage=dir.join("stage.txt");let _=fs::remove_file(&status);let _=fs::remove_file(&stage);
  let stdout=OpenOptions::new().create(true).truncate(true).write(true).open(&log).map_err(|e|e.to_string())?;let stderr=stdout.try_clone().map_err(|e|e.to_string())?;
  let child=Command::new("/bin/bash").arg(&script).env("ENDLUME_GUI_UPDATE","1").env("ENDLUME_UPDATE_STATUS_FILE",&stage).env("ENDLUME_UPDATE_EXIT_FILE",&status).stdin(Stdio::null()).stdout(Stdio::from(stdout)).stderr(Stdio::from(stderr)).spawn().map_err(|e|e.to_string())?;
  Ok(UpdateStart{pid:child.id(),version,log_path:log.to_string_lossy().into_owned()})
}

#[tauri::command]
pub fn local_update_status(app:AppHandle,pid:u32)->Result<UpdateStatus,String>{
  let dir=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("background-updater");let status=dir.join("exit-code.txt");let stage_file=dir.join("stage.txt");let log=dir.join("ENDLUME-update.log");
  let stage=fs::read_to_string(&stage_file).unwrap_or_else(|_|"Подготавливаю обновление".into()).trim().to_string();
  if status.is_file(){
    let code=fs::read_to_string(&status).unwrap_or_else(|_|"1".into()).trim().parse::<i32>().unwrap_or(1);
    let error=if code==0{None}else{let mut s=String::new();if let Ok(mut f)=File::open(&log){let _=f.read_to_string(&mut s);}Some(s.lines().rev().take(8).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\n"))};
    return Ok(UpdateStatus{running:false,done:code==0,failed:code!=0,progress:if code==0{100.0}else{stage_progress(&stage)},stage,error})
  }
  let running=Command::new("/bin/kill").args(["-0",&pid.to_string()]).status().map(|s|s.success()).unwrap_or(false);
  Ok(UpdateStatus{running,done:false,failed:!running,progress:stage_progress(&stage),stage,error:if running{None}else{Some("Фоновая сборка завершилась без статуса. Открой Настройки → Обновления и повтори.".into())}})
}
