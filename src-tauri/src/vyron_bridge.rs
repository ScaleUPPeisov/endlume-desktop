use chrono::Utc;
use serde::{Deserialize,Serialize};
use serde_json::Value;
use std::{collections::HashSet,fs,path::{Path,PathBuf},sync::{Mutex,OnceLock}};
use tauri::{AppHandle,Manager};

static STATUS_LOCK:OnceLock<Mutex<()>>=OnceLock::new();
fn lock()->&'static Mutex<()>{STATUS_LOCK.get_or_init(||Mutex::new(()))}
fn atomic_write(path:&Path,value:&Value)->Result<(),String>{
  let parent=path.parent().ok_or_else(||"Некорректный путь status.json".to_string())?;fs::create_dir_all(parent).map_err(|e|e.to_string())?;
  let tmp=parent.join(format!(".{}.tmp",path.file_name().and_then(|x|x.to_str()).unwrap_or("status.json")));
  fs::write(&tmp,serde_json::to_vec_pretty(value).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
  if path.exists(){let _=fs::remove_file(path);}fs::rename(tmp,path).map_err(|e|e.to_string())
}
fn read_value(path:&Path)->Result<Value,String>{serde_json::from_slice(&fs::read(path).map_err(|e|format!("{}: {e}",path.display()))?).map_err(|e|format!("JSON {}: {e}",path.display()))}
fn string(v:&Value,key:&str)->Result<String,String>{v.get(key).and_then(Value::as_str).filter(|x|!x.trim().is_empty()).map(str::to_string).ok_or_else(||format!("batch.json: поле {key} отсутствует"))}

#[derive(Clone,Debug,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct VyronBatchRequest{pub batch_id:String,pub manifest_path:String,pub requested_at:Option<String>}
#[derive(Clone,Debug,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct VyronBatchInfo{pub batch_id:String,pub channel_id:String,pub channel_name:String,pub project_count:usize,pub tracks_assigned:usize,pub root_path:String,pub output_dir:String,pub status_path:String,pub manifest_path:String}

fn validate_manifest(path:&str)->Result<(Value,PathBuf,PathBuf),String>{
  let manifest=PathBuf::from(path).canonicalize().map_err(|_|"VYRON batch.json не найден".to_string())?;if !manifest.is_file(){return Err("VYRON manifest должен быть файлом".into())}
  let value=read_value(&manifest)?;let source=string(&value,"source")?;if !source.starts_with("VYRON Production Manager"){return Err("Manifest не принадлежит VYRON Production Manager".into())}
  let root=PathBuf::from(string(&value,"rootPath")?).canonicalize().map_err(|_|"Корневая папка VYRON batch не найдена".to_string())?;
  let parent=manifest.parent().ok_or_else(||"Некорректный manifest path".to_string())?.canonicalize().map_err(|e|e.to_string())?;if root!=parent{return Err("VYRON manifest находится вне своей batch-папки".into())}
  Ok((value,manifest,root))
}

#[tauri::command]
pub fn consume_vyron_batch_request(app:AppHandle)->Result<Option<VyronBatchRequest>,String>{
  let inbox=app.path().app_data_dir().map_err(|e|e.to_string())?.join("VYRON Inbox");fs::create_dir_all(&inbox).map_err(|e|e.to_string())?;
  let mut files=fs::read_dir(&inbox).map_err(|e|e.to_string())?.filter_map(Result::ok).map(|e|e.path()).filter(|p|p.is_file()&&p.extension().and_then(|x|x.to_str())==Some("json")).collect::<Vec<_>>();
  files.sort_by_key(|p|fs::metadata(p).ok().and_then(|m|m.modified().ok()));
  for p in files{
    let req:VyronBatchRequest=match serde_json::from_slice(&fs::read(&p).map_err(|e|e.to_string())?){Ok(v)=>v,Err(_)=>{let _=fs::remove_file(&p);continue}};
    validate_manifest(&req.manifest_path)?;let _=fs::remove_file(&p);return Ok(Some(req));
  }
  Ok(None)
}

#[tauri::command]
pub fn load_vyron_batch_manifest(manifest_path:String)->Result<VyronBatchInfo,String>{
  let(v,manifest,root)=validate_manifest(&manifest_path)?;let projects=v.get("projects").and_then(Value::as_array).ok_or_else(||"batch.json: projects отсутствует".to_string())?;
  let declared=v.get("projectCount").and_then(Value::as_u64).unwrap_or(projects.len() as u64) as usize;if declared!=projects.len(){return Err(format!("VYRON batch: projectCount {declared}, фактически {}",projects.len()))}
  let mut folders=HashSet::new();let mut tracks=0usize;
  for p in projects{let folder=PathBuf::from(string(p,"folderPath")?).canonicalize().map_err(|_|"VYRON project folder не найден".to_string())?;if !folder.starts_with(&root){return Err("Проект VYRON находится вне batch root".into())}if !folders.insert(folder){return Err("VYRON batch содержит повтор папки проекта".into())}tracks+=p.get("tracks").and_then(Value::as_array).map(|x|x.len()).unwrap_or(0);}
  let output=PathBuf::from(string(&v,"outputDir")?);fs::create_dir_all(&output).map_err(|e|format!("Output dir: {e}"))?;let output=output.canonicalize().map_err(|e|e.to_string())?;if !output.starts_with(&root){return Err("Output VYRON находится вне batch root".into())}
  let status=PathBuf::from(string(&v,"statusPath")?);let status_parent=status.parent().ok_or_else(||"statusPath некорректен".to_string())?.canonicalize().map_err(|e|e.to_string())?;if status_parent!=root{return Err("statusPath VYRON находится вне batch root".into())}
  Ok(VyronBatchInfo{batch_id:string(&v,"batchId")?,channel_id:string(&v,"channelId")?,channel_name:string(&v,"channelName")?,project_count:projects.len(),tracks_assigned:tracks,root_path:root.to_string_lossy().into_owned(),output_dir:output.to_string_lossy().into_owned(),status_path:status.to_string_lossy().into_owned(),manifest_path:manifest.to_string_lossy().into_owned()})
}

#[tauri::command]
pub fn report_vyron_render(manifest_path:String,project_path:String,render_status:String,output_file:Option<String>,duration:Option<f64>,file_size:Option<u64>,error:Option<String>)->Result<(),String>{
  let _g=lock().lock().map_err(|_|"VYRON status lock".to_string())?;let(v,_,root)=validate_manifest(&manifest_path)?;let status_path=PathBuf::from(string(&v,"statusPath")?);let project=PathBuf::from(&project_path).canonicalize().map_err(|_|"VYRON project path не найден".to_string())?;if !project.starts_with(&root){return Err("Отчёт ENDLUME указывает проект вне VYRON batch".into())}
  let projects=v.get("projects").and_then(Value::as_array).ok_or_else(||"batch projects отсутствуют".to_string())?;let meta=projects.iter().find(|p|PathBuf::from(p.get("folderPath").and_then(Value::as_str).unwrap_or("")).canonicalize().ok().as_ref()==Some(&project)).ok_or_else(||"Проект ENDLUME не найден в VYRON manifest".to_string())?;let project_id=string(meta,"projectId")?;
  let mut status=read_value(&status_path)?;let rows=status.get_mut("projects").and_then(Value::as_array_mut).ok_or_else(||"status.json: projects отсутствует".to_string())?;let row=rows.iter_mut().find(|x|x.get("projectId").and_then(Value::as_str)==Some(project_id.as_str())).ok_or_else(||"status.json: projectId не найден".to_string())?;
  row["renderStatus"]=Value::String(render_status.clone());row["outputFile"]=output_file.map(Value::String).unwrap_or(Value::Null);row["duration"]=duration.and_then(serde_json::Number::from_f64).map(Value::Number).unwrap_or(Value::Null);row["fileSize"]=file_size.map(|x|Value::Number(x.into())).unwrap_or(Value::Null);row["error"]=error.map(Value::String).unwrap_or(Value::Null);
  let all_done=rows.iter().all(|x|x.get("renderStatus").and_then(Value::as_str)==Some("Completed"));let any_render=rows.iter().any(|x|x.get("renderStatus").and_then(Value::as_str)==Some("Rendering"));let any_error=rows.iter().any(|x|x.get("renderStatus").and_then(Value::as_str)==Some("Error"));
  status["status"]=Value::String(if all_done{"Completed"}else if any_render{"Rendering"}else if any_error{"Error"}else{"Передано ENDLUME"}.into());status["updatedAt"]=Value::String(Utc::now().to_rfc3339());atomic_write(&status_path,&status)
}
