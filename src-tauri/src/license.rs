use serde_json::{json,Value};
use sha2::{Digest,Sha256};
use std::fs;
use tauri::{AppHandle,Emitter,Manager};

#[cfg(not(target_os="windows"))]
const OWNER_HASH:&str="4b5631d4a5b7018be7c5237994ad4ba463a4fc1df33165beab0fedc901733ef9";

fn file(app:&AppHandle)->Result<std::path::PathBuf,String>{
  let d=app.path().app_data_dir().map_err(|e|e.to_string())?;
  fs::create_dir_all(&d).map_err(|e|e.to_string())?;
  Ok(d.join("license.json"))
}
fn write_value_atomic(path:&std::path::Path,value:&Value)->Result<(),String>{
  let tmp=path.with_extension("tmp");
  fs::write(&tmp,serde_json::to_vec_pretty(value).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
  if path.exists(){let _=fs::remove_file(path);}
  fs::rename(tmp,path).map_err(|e|e.to_string())
}
fn read_value(app:&AppHandle)->Value{
  file(app).ok().and_then(|p|fs::read(p).ok()).and_then(|b|serde_json::from_slice::<Value>(&b).ok()).unwrap_or(json!({"valid":false}))
}
fn mask(key:&str)->String{
  let key=key.trim();
  if key.starts_with("ENDLUME-")&&key.len()>=12{format!("ENDLUME-••••-••••-••••-{}",&key[key.len()-4..])}
  else if key.len()<9{"••••".into()}else{format!("{}••••{}",&key[..4],&key[key.len()-4..])}
}

#[cfg(not(target_os="windows"))]
fn legacy_status(app:&AppHandle)->Value{read_value(app)}
#[cfg(not(target_os="windows"))]
fn legacy_activate(app:&AppHandle,key:String)->Result<Value,String>{
  let key=key.trim();if key.is_empty(){return Err("Введите ключ ENDLUME".into())}
  let digest=hex::encode(Sha256::digest(key.as_bytes()));
  let v=if digest==OWNER_HASH{
    json!({"valid":true,"type":"owner-lifetime","expiresAt":null,"maskedKey":mask(key),"activatedAt":chrono::Utc::now(),"offlineUntil":null})
  }else{return Err("Ключ не найден.".into())};
  write_value_atomic(&file(app)?,&v)?;Ok(v)
}

#[cfg(target_os="windows")]
mod managed{
  use super::*;
  use crate::model::QueueJob;
  use keyring::Entry;
  use parking_lot::Mutex;
  use std::{collections::HashMap,path::Path,sync::{OnceLock,atomic::{AtomicBool,AtomicI64,Ordering}},time::Duration};

  const CLIENT_API:&str="https://odlseljmogaguyqdlkyv.supabase.co/functions/v1/endlume-client-api";
  const KEYRING_SERVICE:&str="studio.endlume.desktop";
  const KEYRING_USER:&str="managed-session";
  const MANAGED_GRACE_MS:i64=15*60*1000;
  const OWNER_GRACE_MS:i64=7*24*60*60*1000;
  const HEARTBEAT_SECS:u64=25;
  const FRESH_START_GATE_MS:i64=60_000;

  static REMOTE_BLOCKED:AtomicBool=AtomicBool::new(false);
  static LAST_REMOTE_OK_MS:AtomicI64=AtomicI64::new(0);
  static TOKEN_CACHE:OnceLock<Mutex<TokenCache>>=OnceLock::new();
  static KEYRING_SERIAL:OnceLock<Mutex<()>>=OnceLock::new();
  static ACTIVITY:OnceLock<Mutex<Activity>>=OnceLock::new();
  static PROGRESS_SENT:OnceLock<Mutex<HashMap<String,i64>>>=OnceLock::new();

  #[derive(Default)] struct TokenCache{loaded:bool,token:Option<String>}
  #[derive(Clone,Default)] struct Activity{screen:Option<String>,render_status:Option<String>,job_id:Option<String>,progress:Option<f64>}

  fn now_ms()->i64{chrono::Utc::now().timestamp_millis()}
  fn cache()->&'static Mutex<TokenCache>{TOKEN_CACHE.get_or_init(||Mutex::new(TokenCache::default()))}
  fn activity()->&'static Mutex<Activity>{ACTIVITY.get_or_init(||Mutex::new(Activity::default()))}
  fn progress_sent()->&'static Mutex<HashMap<String,i64>>{PROGRESS_SENT.get_or_init(||Mutex::new(HashMap::new()))}
  fn keyring_entry()->Result<Entry,String>{Entry::new(KEYRING_SERVICE,KEYRING_USER).map_err(|e|format!("Secure storage недоступен: {e}"))}
  fn load_token()->Result<Option<String>,String>{
    {let c=cache().lock();if c.loaded{return Ok(c.token.clone())}}
    let _guard=KEYRING_SERIAL.get_or_init(||Mutex::new(())).lock();
    let token=keyring_entry()?.get_password().ok().filter(|x|!x.trim().is_empty());
    let mut c=cache().lock();c.loaded=true;c.token=token.clone();Ok(token)
  }
  fn save_token(token:&str)->Result<(),String>{
    let _guard=KEYRING_SERIAL.get_or_init(||Mutex::new(())).lock();
    keyring_entry()?.set_password(token).map_err(|e|format!("Не удалось сохранить session token в Windows Credential Manager: {e}"))?;
    let mut c=cache().lock();c.loaded=true;c.token=Some(token.to_string());Ok(())
  }
  fn clear_token(){
    let _guard=KEYRING_SERIAL.get_or_init(||Mutex::new(())).lock();
    if let Ok(e)=keyring_entry(){let _=e.delete_credential();}
    let mut c=cache().lock();c.loaded=true;c.token=None;
  }
  fn device_path(app:&AppHandle)->Result<std::path::PathBuf,String>{
    let d=app.path().app_data_dir().map_err(|e|e.to_string())?;fs::create_dir_all(&d).map_err(|e|e.to_string())?;Ok(d.join("device.json"))
  }
  fn device_id(app:&AppHandle)->Result<String,String>{
    let p=device_path(app)?;
    if let Ok(bytes)=fs::read(&p){if let Ok(v)=serde_json::from_slice::<Value>(&bytes){if let Some(id)=v.get("deviceId").and_then(Value::as_str).filter(|x|!x.trim().is_empty()){return Ok(id.to_string())}}}
    let id=uuid::Uuid::new_v4().to_string();write_value_atomic(&p,&json!({"deviceId":id,"createdAt":chrono::Utc::now()}))?;Ok(id)
  }
  fn device_name()->String{std::env::var("COMPUTERNAME").ok().filter(|x|!x.trim().is_empty()).unwrap_or_else(||"Windows device".into())}
  fn normalized_key(key:&str)->String{key.chars().filter(|c|!c.is_whitespace()).collect::<String>().to_uppercase()}
  fn friendly(code:&str)->String{match code{
    "key_format"=>"Неверный формат ключа ENDLUME.",
    "key_invalid"=>"Ключ ENDLUME не найден.",
    "license_paused"=>"Лицензия ENDLUME поставлена на паузу владельцем.",
    "license_revoked"=>"Лицензия ENDLUME отозвана владельцем.",
    "license_expired"=>"Срок лицензии ENDLUME истёк.",
    "device_blocked"=>"Это устройство заблокировано владельцем лицензии.",
    "device_limit"=>"Достигнут лимит устройств этой лицензии.",
    "session_expired"|"session_invalid"=>"Сессия лицензии истекла. Введите ключ повторно.",
    _=>"Сервер лицензий ENDLUME отклонил запрос."
  }.into()}
  fn grace_ms(local:&Value)->i64{if local.get("type").and_then(Value::as_str)==Some("owner-lifetime"){OWNER_GRACE_MS}else{MANAGED_GRACE_MS}}
  fn offline_until(last:i64,grace:i64)->String{chrono::DateTime::<chrono::Utc>::from_timestamp_millis(last+grace).unwrap_or_else(chrono::Utc::now).to_rfc3339()}
  fn server_state(local:&Value,v:&Value,allowed:bool)->Value{
    let owner=v.get("owner").and_then(Value::as_bool).unwrap_or(false);
    let last=now_ms();let grace=if owner{OWNER_GRACE_MS}else{MANAGED_GRACE_MS};
    json!({
      "valid":allowed,
      "type":if owner{"owner-lifetime"}else{"monthly"},
      "plan":v.get("plan").cloned().unwrap_or(Value::Null),
      "licenseId":v.get("licenseId").cloned().unwrap_or(Value::Null),
      "licenseStatus":v.get("licenseStatus").cloned().unwrap_or(Value::Null),
      "expiresAt":v.get("expiresAt").cloned().unwrap_or(Value::Null),
      "maskedKey":local.get("maskedKey").cloned().unwrap_or(Value::Null),
      "deviceId":v.get("deviceId").cloned().unwrap_or(Value::Null),
      "deviceRecordId":v.get("deviceRecordId").cloned().unwrap_or(Value::Null),
      "deviceStatus":v.get("deviceStatus").cloned().unwrap_or(Value::Null),
      "realtimeTopic":v.get("realtimeTopic").cloned().unwrap_or(Value::Null),
      "connection":"online",
      "lastServerOkAt":last,
      "offlineUntil":offline_until(last,grace)
    })
  }
  async fn post(action:&str,mut body:Value,token:Option<&str>,timeout:u64)->Result<(u16,Value),String>{
    if let Some(o)=body.as_object_mut(){o.insert("action".into(),Value::String(action.into()));}
    let client=reqwest::Client::builder().timeout(Duration::from_secs(timeout)).build().map_err(|e|e.to_string())?;
    let mut req=client.post(CLIENT_API).header("Content-Type","application/json").json(&body);
    if let Some(t)=token{req=req.header("x-endlume-session",t)}
    let resp=req.send().await.map_err(|e|format!("Сервер лицензий недоступен: {e}"))?;let status=resp.status().as_u16();
    let text=resp.text().await.map_err(|e|e.to_string())?;let value=serde_json::from_str::<Value>(&text).unwrap_or_else(|_|json!({"ok":false,"code":"bad_response"}));Ok((status,value))
  }
  fn persist(app:&AppHandle,v:&Value){if let Ok(p)=file(app){let _=write_value_atomic(&p,v);}}
  fn mark_remote(app:&AppHandle,allowed:bool,state:&Value){
    let blocked=!allowed;let was=REMOTE_BLOCKED.swap(blocked,Ordering::SeqCst);
    if was!=blocked{let _=app.emit("license-state-changed",state.clone());}
  }
  fn offline_fallback(app:&AppHandle,local:Value,error:String)->Value{
    let last=local.get("lastServerOkAt").and_then(Value::as_i64).unwrap_or(0);let grace=grace_ms(&local);let allowed=local.get("valid").and_then(Value::as_bool).unwrap_or(false)&&last>0&&now_ms()-last<=grace;
    let mut next=local;if let Some(o)=next.as_object_mut(){o.insert("valid".into(),Value::Bool(allowed));o.insert("connection".into(),Value::String(if allowed{"offline-grace"}else{"offline-blocked"}.into()));o.insert("offlineUntil".into(),Value::String(offline_until(last,grace)));o.insert("connectionError".into(),Value::String(error));}
    persist(app,&next);mark_remote(app,allowed,&next);next
  }
  pub async fn status(app:&AppHandle,heartbeat:bool)->Value{
    let local=read_value(app);let token=match load_token(){Ok(Some(t))=>t,_=>{let v=json!({"valid":false,"connection":"not-activated"});mark_remote(app,false,&v);return v}};
    let body=if heartbeat{let a=activity().lock().clone();json!({"app_version":env!("CARGO_PKG_VERSION"),"current_screen":a.screen,"render_status":a.render_status,"current_job_id":a.job_id,"progress":a.progress})}else{json!({})};
    match post(if heartbeat{"heartbeat"}else{"status"},body,Some(&token),6).await{
      Ok((http,v)) if (200..300).contains(&http)&&v.get("ok").and_then(Value::as_bool).unwrap_or(false)=>{
        let allowed=v.get("allowed").and_then(Value::as_bool).unwrap_or(false);if allowed{LAST_REMOTE_OK_MS.store(now_ms(),Ordering::SeqCst)}
        let next=server_state(&local,&v,allowed);persist(app,&next);mark_remote(app,allowed,&next);next
      }
      Ok((_http,v))=>{
        let code=v.get("code").and_then(Value::as_str).unwrap_or("denied");if matches!(code,"session_invalid"|"session_expired"|"binding_missing"){clear_token()}
        let next=json!({"valid":false,"connection":"blocked","reason":friendly(code),"code":code,"maskedKey":local.get("maskedKey").cloned().unwrap_or(Value::Null)});persist(app,&next);mark_remote(app,false,&next);next
      }
      Err(e)=>offline_fallback(app,local,e)
    }
  }
  pub async fn activate(app:&AppHandle,key:String)->Result<Value,String>{
    let key=normalized_key(&key);if key.is_empty(){return Err("Введите ключ ENDLUME".into())}
    let id=device_id(app)?;let body=json!({"key":key,"device_id":id,"platform":"windows","architecture":std::env::consts::ARCH,"app_version":env!("CARGO_PKG_VERSION"),"device_name":device_name()});
    let (http,v)=post("activate",body,None,12).await?;
    if !(200..300).contains(&http)||!v.get("ok").and_then(Value::as_bool).unwrap_or(false){let code=v.get("code").and_then(Value::as_str).unwrap_or("denied");return Err(friendly(code))}
    let token=v.get("sessionToken").and_then(Value::as_str).filter(|x|!x.is_empty()).ok_or("Сервер не вернул session token")?;save_token(token)?;
    let owner=v.get("owner").and_then(Value::as_bool).unwrap_or(false);let last=now_ms();let grace=if owner{OWNER_GRACE_MS}else{MANAGED_GRACE_MS};
    let next=json!({"valid":true,"type":if owner{"owner-lifetime"}else{"monthly"},"plan":v.get("plan").cloned().unwrap_or(Value::Null),"licenseId":v.get("licenseId").cloned().unwrap_or(Value::Null),"licenseStatus":"active","expiresAt":v.get("expiresAt").cloned().unwrap_or(Value::Null),"maskedKey":mask(&key),"deviceId":id,"deviceRecordId":v.get("deviceRecordId").cloned().unwrap_or(Value::Null),"deviceStatus":v.get("deviceStatus").cloned().unwrap_or(Value::String("active".into())),"realtimeTopic":v.get("realtimeTopic").cloned().unwrap_or(Value::Null),"connection":"online","lastServerOkAt":last,"offlineUntil":offline_until(last,grace),"activatedAt":chrono::Utc::now()});
    LAST_REMOTE_OK_MS.store(last,Ordering::SeqCst);persist(app,&next);mark_remote(app,true,&next);Ok(next)
  }
  pub async fn assert_start(app:&AppHandle)->Result<(),String>{
    if !REMOTE_BLOCKED.load(Ordering::SeqCst){let last=LAST_REMOTE_OK_MS.load(Ordering::SeqCst);if last>0&&now_ms()-last<=FRESH_START_GATE_MS{return Ok(())}}
    let v=status(app,false).await;if v.get("valid").and_then(Value::as_bool).unwrap_or(false){Ok(())}else{Err(v.get("reason").and_then(Value::as_str).unwrap_or("Production render заблокирован лицензией ENDLUME.").to_string())}
  }
  pub fn blocked()->bool{REMOTE_BLOCKED.load(Ordering::SeqCst)}
  pub fn set_screen(screen:String){activity().lock().screen=Some(screen.chars().take(120).collect())}
  pub fn set_render_activity(job_id:Option<String>,status:Option<String>,progress:Option<f64>){let mut a=activity().lock();a.job_id=job_id;a.render_status=status;a.progress=progress.map(|x|x.clamp(0.0,100.0));}
  pub fn start_heartbeat(app:AppHandle){
    tauri::async_runtime::spawn(async move{tokio::time::sleep(Duration::from_secs(2)).await;loop{let _=status(&app,true).await;tokio::time::sleep(Duration::from_secs(HEARTBEAT_SECS)).await;}});
  }
  fn spawn_event(body:Value){
    let token=load_token().ok().flatten();let Some(token)=token else{return};
    tauri::async_runtime::spawn(async move{let _=post("render_event",body,Some(&token),5).await;});
  }
  fn base_event(job:&QueueJob,event_type:&str,progress:f64,eta:Option<f64>,stage:Option<&str>,encoder:Option<&str>)->Value{
    json!({"event_type":event_type,"job_id":job.project.id,"project_id":job.project.id,"project_name":job.project.name,"progress":progress.clamp(0.0,100.0),"eta_seconds":eta,"stage":stage,"encoder":encoder,"width":job.settings.width,"height":job.settings.height,"fps":job.settings.fps,"codec":job.settings.codec,"audio_count":job.project.audio.len(),"effects_count":job.effects.iter().filter(|x|x.enabled).count(),"subscribe_enabled":job.subscribes.iter().any(|x|x.effect.enabled),"app_version":env!("CARGO_PKG_VERSION"),"settings":{"durationMode":job.settings.duration_mode,"durationHours":job.settings.duration_hours,"crossfadeSec":job.settings.crossfade_sec,"normalizeLufs":job.settings.normalize_lufs,"preset":job.settings.preset,"encoderPreference":job.settings.encoder_preference}})
  }
  pub fn render_started(job:&QueueJob){set_render_activity(Some(job.project.id.clone()),Some("rendering".into()),Some(0.0));spawn_event(base_event(job,"render_started",0.0,None,Some("Starting"),None));}
  pub fn render_progress(job:&QueueJob,progress:f64,eta:Option<f64>,stage:&str,encoder:&str){
    set_render_activity(Some(job.project.id.clone()),Some("rendering".into()),Some(progress));let now=now_ms();{let mut m=progress_sent().lock();let last=*m.get(&job.project.id).unwrap_or(&0);if progress<99.0&&now-last<1000{return}m.insert(job.project.id.clone(),now);}spawn_event(base_event(job,"render_progress",progress,eta,Some(stage),Some(encoder)));
  }
  pub fn render_terminal(job:&QueueJob,event_type:&str,output:Option<&str>,bytes:Option<u64>,error:Option<&str>,duration:Option<f64>){
    let status=match event_type{"render_completed"=>"completed","render_cancelled"=>"cancelled",_=>"failed"};let progress=if event_type=="render_completed"{100.0}else{0.0};set_render_activity(None,Some(status.into()),Some(progress));progress_sent().lock().remove(&job.project.id);let mut body=base_event(job,event_type,progress,Some(0.0),Some(status),None);if let Some(o)=body.as_object_mut(){o.insert("output_filename".into(),output.and_then(|p|Path::new(p).file_name()).and_then(|x|x.to_str()).map(|x|Value::String(x.to_string())).unwrap_or(Value::Null));o.insert("output_bytes".into(),bytes.map(|x|json!(x)).unwrap_or(Value::Null));o.insert("error".into(),error.map(|x|Value::String(x.chars().take(4000).collect())).unwrap_or(Value::Null));o.insert("duration_seconds".into(),duration.map(|x|json!(x.max(0.0))).unwrap_or(Value::Null));}spawn_event(body)
  }
}

#[tauri::command]
pub async fn license_status(app:AppHandle)->Value{
  #[cfg(target_os="windows")]{return managed::status(&app,false).await}
  #[cfg(not(target_os="windows"))]{legacy_status(&app)}
}
#[tauri::command]
pub async fn activate_license(app:AppHandle,key:String)->Result<Value,String>{
  #[cfg(target_os="windows")]{return managed::activate(&app,key).await}
  #[cfg(not(target_os="windows"))]{legacy_activate(&app,key)}
}
#[tauri::command]
pub fn set_license_screen(screen:String){
  #[cfg(target_os="windows")]{managed::set_screen(screen)}
  #[cfg(not(target_os="windows"))]{let _=screen;}
}
pub async fn assert_production_allowed(app:&AppHandle)->Result<(),String>{
  #[cfg(target_os="windows")]{return managed::assert_start(app).await}
  #[cfg(not(target_os="windows"))]{if legacy_status(app).get("valid").and_then(Value::as_bool).unwrap_or(false){Ok(())}else{Err("ENDLUME не активирован.".into())}}
}
pub fn production_blocked()->bool{
  #[cfg(target_os="windows")]{return managed::blocked()}
  #[cfg(not(target_os="windows"))]{false}
}
pub fn start_heartbeat(app:AppHandle){
  #[cfg(target_os="windows")]{managed::start_heartbeat(app)}
  #[cfg(not(target_os="windows"))]{let _=app;}
}
pub fn telemetry_render_started(job:&crate::model::QueueJob){
  #[cfg(target_os="windows")]{managed::render_started(job)}
  #[cfg(not(target_os="windows"))]{let _=job;}
}
pub fn telemetry_render_progress(job:&crate::model::QueueJob,progress:f64,eta:Option<f64>,stage:&str,encoder:&str){
  #[cfg(target_os="windows")]{managed::render_progress(job,progress,eta,stage,encoder)}
  #[cfg(not(target_os="windows"))]{let _=(job,progress,eta,stage,encoder);}
}
pub fn telemetry_render_terminal(job:&crate::model::QueueJob,event_type:&str,output:Option<&str>,bytes:Option<u64>,error:Option<&str>,duration:Option<f64>){
  #[cfg(target_os="windows")]{managed::render_terminal(job,event_type,output,bytes,error,duration)}
  #[cfg(not(target_os="windows"))]{let _=(job,event_type,output,bytes,error,duration);}
}
