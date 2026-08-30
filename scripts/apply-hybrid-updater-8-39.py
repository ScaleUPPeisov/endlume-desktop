from pathlib import Path

UPDATER = r'''use serde::{Deserialize,Serialize};
use std::{fs,path::{Path,PathBuf},process::{Command,Stdio}};
use tauri::{AppHandle,Manager};

const REPO:&str="ScaleUPPeisov/endlume-desktop";
const BRANCH:&str="release";
const MANIFEST_PATH:&str="updates/latest.json";
const DEST_APP:&str="/Applications/ENDLUME Studio.app";

#[derive(Debug,Clone,Deserialize)]
#[serde(rename_all="camelCase")]
struct UpdateManifest{
  version:String,
  #[serde(default)] builder:String,
  #[serde(default)] notes:String,
  #[serde(default)] date:String,
  #[serde(default)] channel:String,
  #[serde(default)] release_tag:String,
  #[serde(default)] asset:String,
  #[serde(default)] checksum_asset:String,
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
  fs::create_dir_all(&p).map_err(|e|e.to_string())?;Ok(p)
}
fn gh_auth_ok(gh:&Path)->bool{
  Command::new(gh).args(["auth","status","-h","github.com"]).stdout(Stdio::null()).stderr(Stdio::null()).status().map(|s|s.success()).unwrap_or(false)
}
fn gh_raw(gh:&Path,path:&str)->Result<Vec<u8>,String>{
  let endpoint=format!("/repos/{REPO}/contents/{path}?ref={BRANCH}");
  let out=Command::new(gh).args(["api","-H","Accept: application/vnd.github.raw+json",&endpoint]).output().map_err(|e|format!("Не удалось запустить GitHub CLI: {e}"))?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}Ok(out.stdout)
}
fn manifest(gh:&Path)->Result<UpdateManifest,String>{
  serde_json::from_slice(&gh_raw(gh,MANIFEST_PATH)?).map_err(|e|format!("Некорректный update manifest: {e}"))
}
fn version_parts(v:&str)->Vec<u64>{v.split(|c:char|!c.is_ascii_digit()).filter(|s|!s.is_empty()).filter_map(|s|s.parse().ok()).collect()}
fn is_newer(candidate:&str,current:&str)->bool{
  let a=version_parts(candidate);let b=version_parts(current);let n=a.len().max(b.len());
  for i in 0..n{let av=*a.get(i).unwrap_or(&0);let bv=*b.get(i).unwrap_or(&0);if av>bv{return true}if av<bv{return false}}false
}
fn write_state(path:&Path,status:&LocalUpdateStatus)->Result<(),String>{
  fs::write(path,serde_json::to_vec(status).map_err(|e|e.to_string())?).map_err(|e|e.to_string())
}
#[cfg(unix)]
fn make_exec(path:&Path)->Result<(),String>{
  use std::os::unix::fs::PermissionsExt;
  let mut p=fs::metadata(path).map_err(|e|e.to_string())?.permissions();p.set_mode(0o755);fs::set_permissions(path,p).map_err(|e|e.to_string())
}
#[cfg(not(unix))]
fn make_exec(_path:&Path)->Result<(),String>{Ok(())}

fn remote_release_ready(gh:&Path,m:&UpdateManifest)->bool{
  if m.release_tag.trim().is_empty()||m.asset.trim().is_empty()||m.checksum_asset.trim().is_empty(){return false}
  let out=Command::new(gh).args(["release","view",m.release_tag.as_str(),"--repo",REPO,"--json","assets","--jq",".assets[].name"]).output();
  let Ok(out)=out else{return false};if !out.status.success(){return false}
  let names=String::from_utf8_lossy(&out.stdout);
  names.lines().any(|x|x.trim()==m.asset)&&names.lines().any(|x|x.trim()==m.checksum_asset)
}
fn valid_builder(name:&str)->bool{
  name.starts_with("BUILD_ENDLUME_")&&(name.ends_with("_LOCAL.command")||name.ends_with("_CI.command"))&&!name.contains('/')&&!name.contains("..")
}

#[tauri::command]
pub fn local_update_check()->LocalUpdateInfo{
  let current=env!("CARGO_PKG_VERSION").to_string();
  let Some(gh)=gh_path() else{return LocalUpdateInfo{supported:false,available:false,current,version:None,notes:None,date:None,reason:Some("GitHub CLI не найден. Update Center требует bootstrap-компонент.".into())}};
  if !gh_auth_ok(&gh){return LocalUpdateInfo{supported:false,available:false,current,version:None,notes:None,date:None,reason:Some("GitHub CLI не авторизован. ENDLUME не может прочитать приватный канал обновлений.".into())}}
  match manifest(&gh){
    Ok(m)=>LocalUpdateInfo{supported:true,available:is_newer(&m.version,&current),current,version:Some(m.version),notes:Some(m.notes),date:Some(m.date),reason:None},
    Err(e)=>LocalUpdateInfo{supported:true,available:false,current,version:None,notes:None,date:None,reason:Some(e)},
  }
}

fn launch_remote(app:&AppHandle,gh:&Path,m:&UpdateManifest,dir:&Path,log:&Path,state:&Path)->Result<LocalUpdateStatus,String>{
  let launcher=dir.join("install-remote-update.sh");
  let initial=LocalUpdateStatus{state:"starting".into(),stage:Some("Скачиваю готовую ENDLUME".into()),progress:2.0,message:Some(format!("ENDLUME {}",m.version)),log_path:Some(log.to_string_lossy().into_owned())};write_state(state,&initial)?;
  let shell=r#"#!/bin/bash
set -Eeuo pipefail
write_state(){ /usr/bin/python3 - "$STATE" "$1" "$2" "$3" "$4" "$LOG" <<'PY'
import json,sys
path,state,stage,progress,message,log=sys.argv[1:]
with open(path,'w',encoding='utf-8') as f: json.dump({'state':state,'stage':stage or None,'progress':float(progress),'message':message or None,'logPath':log},f,ensure_ascii=False)
PY
}
fail_state(){ code=$?; write_state failed "Обновление остановлено" 0 "Код $code. См. update.log"; exit $code; }
trap fail_state ERR
rm -rf "$UPDATE_DIR/download" "$UPDATE_DIR/stage" "$NEW" >/dev/null 2>&1 || true
mkdir -p "$UPDATE_DIR/download" "$UPDATE_DIR/stage"
write_state running "Скачиваю готовую ENDLUME" 15 ""
"$GH" release download "$TAG" --repo "$REPO" --pattern "$ASSET" --pattern "$CHECKSUM_ASSET" --dir "$UPDATE_DIR/download" --clobber
PACKAGE="$UPDATE_DIR/download/$ASSET"; CHECKSUM="$UPDATE_DIR/download/$CHECKSUM_ASSET"; test -s "$PACKAGE"; test -s "$CHECKSUM"
write_state running "Проверяю SHA-256" 35 ""
(cd "$UPDATE_DIR/download" && /usr/bin/shasum -a 256 -c "$CHECKSUM_ASSET")
write_state running "Распаковываю приложение" 48 ""
/usr/bin/ditto -x -k "$PACKAGE" "$UPDATE_DIR/stage"
APP="$(/usr/bin/find "$UPDATE_DIR/stage" -maxdepth 4 -type d -name 'ENDLUME Studio.app' -print -quit)"; test -n "$APP"; test -d "$APP"
test "$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$APP/Contents/Info.plist")" = "studio.endlume.desktop"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$APP/Contents/Info.plist")" = "$EXPECTED_VERSION"
/usr/bin/codesign --verify --deep --strict "$APP"
write_state ready "Готово к установке" 72 ""
rm -rf "$NEW" "$OLD" >/dev/null 2>&1 || true
/usr/bin/ditto "$APP" "$NEW"
write_state installing "Устанавливаю и перезапускаю" 84 ""
/usr/bin/osascript -e 'tell application "ENDLUME Studio" to quit' >/dev/null 2>&1 || true
for _ in $(seq 1 40); do /usr/bin/pgrep -x "ENDLUME Studio" >/dev/null 2>&1 || break; /bin/sleep 0.25; done
if [ -d "$DEST" ]; then /bin/mv "$DEST" "$OLD"; fi
if /bin/mv "$NEW" "$DEST"; then :; else [ -d "$OLD" ] && /bin/mv "$OLD" "$DEST"; false; fi
/usr/bin/xattr -dr com.apple.quarantine "$DEST" >/dev/null 2>&1 || true
/usr/bin/codesign --verify --deep --strict "$DEST"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$DEST/Contents/Info.plist")" = "$EXPECTED_VERSION"
write_state success "Обновление установлено" 100 ""
open "$DEST"; /bin/sleep 2; rm -rf "$OLD" >/dev/null 2>&1 || true
"#;
  fs::write(&launcher,shell).map_err(|e|e.to_string())?;make_exec(&launcher)?;
  let log_file=fs::OpenOptions::new().create(true).truncate(true).write(true).open(log).map_err(|e|e.to_string())?;let err_file=log_file.try_clone().map_err(|e|e.to_string())?;
  Command::new("/usr/bin/nohup").arg("/bin/bash").arg(&launcher)
    .env("GH",gh).env("REPO",REPO).env("TAG",&m.release_tag).env("ASSET",&m.asset).env("CHECKSUM_ASSET",&m.checksum_asset)
    .env("UPDATE_DIR",dir).env("STATE",state).env("LOG",log).env("DEST",DEST_APP).env("NEW","/Applications/.ENDLUME Studio.remote-new.app").env("OLD","/Applications/.ENDLUME Studio.remote-previous.app").env("EXPECTED_VERSION",&m.version)
    .stdin(Stdio::null()).stdout(Stdio::from(log_file)).stderr(Stdio::from(err_file)).spawn().map_err(|e|format!("Не удалось запустить remote updater: {e}"))?;
  Ok(initial)
}

fn launch_local(app:&AppHandle,gh:&Path,m:&UpdateManifest,dir:&Path,log:&Path,state:&Path)->Result<LocalUpdateStatus,String>{
  if !valid_builder(&m.builder){return Err("Нет готового binary release и manifest не содержит безопасный local builder".into())}
  let builder=dir.join(&m.builder);let launcher=dir.join("run-local-fallback.sh");
  fs::write(&builder,gh_raw(gh,&m.builder)?).map_err(|e|e.to_string())?;make_exec(&builder)?;
  let initial=LocalUpdateStatus{state:"starting".into(),stage:Some("Готовлю локальное обновление в фоне".into()),progress:2.0,message:Some(format!("ENDLUME {}",m.version)),log_path:Some(log.to_string_lossy().into_owned())};write_state(state,&initial)?;
  let shell=format!(r#"#!/bin/bash
set +e
STATE={state:?}
LOG={log:?}
BUILDER={builder:?}
/usr/bin/python3 - "$STATE" "$LOG" <<'PY'
import json,sys
with open(sys.argv[1],'w',encoding='utf-8') as f: json.dump({{'state':'running','stage':'Проверяю и собираю обновление в фоне','progress':4.0,'message':None,'logPath':sys.argv[2]}},f,ensure_ascii=False)
PY
ENDLUME_IN_APP_UPDATE=1 /bin/bash "$BUILDER" > "$LOG" 2>&1
CODE=$?
/usr/bin/python3 - "$STATE" "$LOG" "$CODE" <<'PY'
import json,sys
code=int(sys.argv[3]); ok=code==0
with open(sys.argv[1],'w',encoding='utf-8') as f: json.dump({{'state':'success' if ok else 'failed','stage':'Обновление установлено' if ok else 'Обновление остановлено','progress':100.0 if ok else 0.0,'message':None if ok else f'Код {{code}}','logPath':sys.argv[2]}},f,ensure_ascii=False)
PY
exit $CODE
"#,state=state.to_string_lossy(),log=log.to_string_lossy(),builder=builder.to_string_lossy());
  fs::write(&launcher,shell).map_err(|e|e.to_string())?;make_exec(&launcher)?;
  let log_file=fs::OpenOptions::new().create(true).truncate(true).write(true).open(log).map_err(|e|e.to_string())?;let err_file=log_file.try_clone().map_err(|e|e.to_string())?;
  Command::new("/usr/bin/nohup").arg("/bin/bash").arg(&launcher).stdin(Stdio::null()).stdout(Stdio::from(log_file)).stderr(Stdio::from(err_file)).spawn().map_err(|e|format!("Не удалось запустить локальный fallback updater: {e}"))?;
  let _=app;Ok(initial)
}

#[tauri::command]
pub fn local_update_start(app:AppHandle)->Result<LocalUpdateStatus,String>{
  let current=env!("CARGO_PKG_VERSION");let gh=gh_path().ok_or("GitHub CLI не найден")?;
  if !gh_auth_ok(&gh){return Err("GitHub CLI не авторизован. Обновление не запущено.".into())}
  let m=manifest(&gh)?;if !is_newer(&m.version,current){return Err(format!("Уже установлена актуальная версия {current}"))}
  let dir=app_update_dir(&app)?;let log=dir.join("update.log");let state=dir.join("state.json");
  if remote_release_ready(&gh,&m){launch_remote(&app,&gh,&m,&dir,&log,&state)}else{launch_local(&app,&gh,&m,&dir,&log,&state)}
}

fn parse_live_stage(log:&str)->(Option<String>,Option<f64>){
  let mut stage=None;let mut progress=None;
  for line in log.lines(){if let Some(v)=line.strip_prefix("@@ENDLUME_STAGE|"){stage=Some(v.trim().to_string())}if let Some(v)=line.strip_prefix("@@ENDLUME_PROGRESS|"){if let Ok(n)=v.trim().parse::<f64>(){progress=Some(n.clamp(0.0,100.0))}}}
  (stage,progress)
}
#[tauri::command]
pub fn local_update_status(app:AppHandle)->Result<LocalUpdateStatus,String>{
  let dir=app_update_dir(&app)?;let state_path=dir.join("state.json");let log_path=dir.join("update.log");
  let mut status=if state_path.is_file(){serde_json::from_slice::<LocalUpdateStatus>(&fs::read(&state_path).map_err(|e|e.to_string())?).unwrap_or(LocalUpdateStatus{state:"unknown".into(),stage:None,progress:0.0,message:None,log_path:None})}else{LocalUpdateStatus{state:"idle".into(),stage:None,progress:0.0,message:None,log_path:None}};
  if log_path.is_file(){if let Ok(raw)=fs::read_to_string(&log_path){let (stage,progress)=parse_live_stage(&raw);if stage.is_some(){status.stage=stage}if let Some(p)=progress{status.progress=p}}status.log_path=Some(log_path.to_string_lossy().into_owned())}Ok(status)
}
'''

Path('src-tauri/src/updater_local.rs').write_text(UPDATER,encoding='utf-8')

# Keep the UI text truthful: binary release first, local validated fallback second.
p=Path('src/pages/SettingsPage.tsx'); s=p.read_text(encoding='utf-8')
s=s.replace('Обновления собираются на удалённом macOS-сервере. Этот Mac только скачивает проверенную готовую ENDLUME, устанавливает её и перезапускает приложение — без npm, Rust и Terminal.', 'Update Center сначала ставит готовую проверенную ENDLUME. Если серверная сборка временно недоступна, ENDLUME сама запускает проверенный локальный fallback в фоне — без ручного Terminal.')
p.write_text(s,encoding='utf-8')

print('ENDLUME 8.39 hybrid updater applied')
