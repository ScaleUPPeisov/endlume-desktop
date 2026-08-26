use serde::{Deserialize,Serialize};
use std::{fs,path::{Path,PathBuf},process::{Command,Stdio}};
use tauri::{AppHandle,Manager};

const REPO:&str="ScaleUPPeisov/endlume-desktop";
const BRANCH:&str="release";
const MANIFEST_PATH:&str="updates/latest.json";

#[derive(Debug,Clone,Deserialize)]
#[serde(rename_all="camelCase")]
struct UpdateManifest{
  version:String,
  builder:String,
  #[serde(default)] notes:String,
  #[serde(default)] date:String,
}

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

fn gh_path()->Option<PathBuf>{
  ["/opt/homebrew/bin/gh","/usr/local/bin/gh","/usr/bin/gh"].iter().map(PathBuf::from).find(|p|p.is_file())
}

fn app_update_dir(app:&AppHandle)->Result<PathBuf,String>{
  let p=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("update-center");
  fs::create_dir_all(&p).map_err(|e|e.to_string())?;
  Ok(p)
}

fn gh_auth_ok(gh:&Path)->bool{
  Command::new(gh).args(["auth","status","-h","github.com"]).stdout(Stdio::null()).stderr(Stdio::null()).status().map(|s|s.success()).unwrap_or(false)
}

fn gh_raw(gh:&Path,path:&str)->Result<Vec<u8>,String>{
  let endpoint=format!("/repos/{REPO}/contents/{path}?ref={BRANCH}");
  let out=Command::new(gh).args(["api","-H","Accept: application/vnd.github.raw+json",&endpoint]).output().map_err(|e|format!("Не удалось запустить GitHub CLI: {e}"))?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
  Ok(out.stdout)
}

fn manifest(gh:&Path)->Result<UpdateManifest,String>{
  let raw=gh_raw(gh,MANIFEST_PATH)?;
  serde_json::from_slice(&raw).map_err(|e|format!("Некорректный update manifest: {e}"))
}

fn version_parts(v:&str)->Vec<u64>{
  v.split(|c:char|!c.is_ascii_digit()).filter(|s|!s.is_empty()).filter_map(|s|s.parse().ok()).collect()
}
fn is_newer(candidate:&str,current:&str)->bool{
  let a=version_parts(candidate);let b=version_parts(current);let n=a.len().max(b.len());
  for i in 0..n{let av=*a.get(i).unwrap_or(&0);let bv=*b.get(i).unwrap_or(&0);if av>bv{return true}if av<bv{return false}}
  false
}

#[tauri::command]
pub fn local_update_check()->LocalUpdateInfo{
  let current=env!("CARGO_PKG_VERSION").to_string();
  let Some(gh)=gh_path() else{return LocalUpdateInfo{supported:false,available:false,current,version:None,notes:None,date:None,reason:Some("GitHub CLI не найден. Нужна одна установка bootstrap-версии ENDLUME.".into())}};
  if !gh_auth_ok(&gh){return LocalUpdateInfo{supported:false,available:false,current,version:None,notes:None,date:None,reason:Some("GitHub CLI не авторизован. ENDLUME не может прочитать приватный канал обновлений.".into())}}
  match manifest(&gh){
    Ok(m)=>LocalUpdateInfo{supported:true,available:is_newer(&m.version,&current),current,version:Some(m.version),notes:Some(m.notes),date:Some(m.date),reason:None},
    Err(e)=>LocalUpdateInfo{supported:true,available:false,current,version:None,notes:None,date:None,reason:Some(e)},
  }
}

#[cfg(unix)]
fn make_exec(path:&Path)->Result<(),String>{
  use std::os::unix::fs::PermissionsExt;
  let mut p=fs::metadata(path).map_err(|e|e.to_string())?.permissions();p.set_mode(0o755);fs::set_permissions(path,p).map_err(|e|e.to_string())
}
#[cfg(not(unix))]
fn make_exec(_path:&Path)->Result<(),String>{Ok(())}

fn write_state(path:&Path,status:&LocalUpdateStatus)->Result<(),String>{
  fs::write(path,serde_json::to_vec(status).map_err(|e|e.to_string())?).map_err(|e|e.to_string())
}

#[tauri::command]
pub fn local_update_start(app:AppHandle)->Result<LocalUpdateStatus,String>{
  let current=env!("CARGO_PKG_VERSION");
  let gh=gh_path().ok_or("GitHub CLI не найден")?;
  if !gh_auth_ok(&gh){return Err("GitHub CLI не авторизован. Обновление не запущено.".into())}
  let m=manifest(&gh)?;
  if !is_newer(&m.version,current){return Err(format!("Уже установлена актуальная версия {current}"))}
  if !m.builder.starts_with("BUILD_ENDLUME_")||!m.builder.ends_with("_LOCAL.command"){return Err("Update manifest содержит недопустимый builder".into())}
  let dir=app_update_dir(&app)?;let builder=dir.join(&m.builder);let log=dir.join("update.log");let state=dir.join("state.json");let launcher=dir.join("run-update.sh");
  fs::write(&builder,gh_raw(&gh,&m.builder)?).map_err(|e|e.to_string())?;make_exec(&builder)?;
  let initial=LocalUpdateStatus{state:"starting".into(),stage:Some("Подготавливаю обновление".into()),progress:1.0,message:Some(format!("ENDLUME {}",m.version)),log_path:Some(log.to_string_lossy().into_owned())};write_state(&state,&initial)?;
  let shell=format!(r#"#!/bin/bash
set +e
STATE={state:?}
LOG={log:?}
BUILDER={builder:?}
cat > "$STATE" <<'JSON'
{{"state":"running","stage":"Запускаю проверку и сборку","progress":3.0,"message":null,"logPath":null}}
JSON
/bin/bash "$BUILDER" > "$LOG" 2>&1
CODE=$?
if [ $CODE -eq 0 ]; then
  cat > "$STATE" <<'JSON'
{{"state":"success","stage":"Обновление установлено","progress":100.0,"message":null,"logPath":null}}
JSON
else
  cat > "$STATE" <<JSON
{{"state":"failed","stage":"Обновление остановлено","progress":0.0,"message":"Код $CODE","logPath":null}}
JSON
fi
exit $CODE
"#,state=state.to_string_lossy(),log=log.to_string_lossy(),builder=builder.to_string_lossy());
  fs::write(&launcher,shell).map_err(|e|e.to_string())?;make_exec(&launcher)?;
  let log_file=fs::OpenOptions::new().create(true).append(true).open(&log).map_err(|e|e.to_string())?;let err_file=log_file.try_clone().map_err(|e|e.to_string())?;
  Command::new("/usr/bin/nohup").arg("/bin/bash").arg(&launcher).stdin(Stdio::null()).stdout(Stdio::from(log_file)).stderr(Stdio::from(err_file)).spawn().map_err(|e|format!("Не удалось запустить обновление: {e}"))?;
  Ok(initial)
}

fn parse_live_stage(log:&str)->(Option<String>,Option<f64>){
  let mut stage=None;let mut progress=None;
  for line in log.lines(){
    if let Some(v)=line.strip_prefix("@@ENDLUME_STAGE|"){stage=Some(v.trim().to_string())}
    if let Some(v)=line.strip_prefix("@@ENDLUME_PROGRESS|"){if let Ok(n)=v.trim().parse::<f64>(){progress=Some(n.clamp(0.0,100.0))}}
  }
  (stage,progress)
}

#[tauri::command]
pub fn local_update_status(app:AppHandle)->Result<LocalUpdateStatus,String>{
  let dir=app_update_dir(&app)?;let state_path=dir.join("state.json");let log_path=dir.join("update.log");
  let mut status=if state_path.is_file(){serde_json::from_slice::<LocalUpdateStatus>(&fs::read(&state_path).map_err(|e|e.to_string())?).unwrap_or(LocalUpdateStatus{state:"unknown".into(),stage:None,progress:0.0,message:None,log_path:None})}else{LocalUpdateStatus{state:"idle".into(),stage:None,progress:0.0,message:None,log_path:None}};
  if log_path.is_file(){if let Ok(raw)=fs::read_to_string(&log_path){let (stage,progress)=parse_live_stage(&raw);if stage.is_some(){status.stage=stage}if let Some(p)=progress{status.progress=p}}status.log_path=Some(log_path.to_string_lossy().into_owned())}
  Ok(status)
}
