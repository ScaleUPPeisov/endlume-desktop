use chrono::Utc;
use serde::{Deserialize,Serialize};
use serde_json::Value;
use std::{collections::{HashMap,HashSet},fs,path::{Path,PathBuf},sync::{Mutex,OnceLock},time::{Duration,SystemTime}};
use tauri::{AppHandle,Manager};

static STATUS_LOCK:OnceLock<Mutex<()>>=OnceLock::new();
static PROJECT_MAP:OnceLock<Mutex<HashMap<String,String>>>=OnceLock::new();
fn lock()->&'static Mutex<()>{STATUS_LOCK.get_or_init(||Mutex::new(()))}
fn project_map()->&'static Mutex<HashMap<String,String>>{PROJECT_MAP.get_or_init(||Mutex::new(HashMap::new()))}
fn atomic_write(path:&Path,value:&Value)->Result<(),String>{
  let parent=path.parent().ok_or_else(||"Некорректный путь status.json".to_string())?;fs::create_dir_all(parent).map_err(|e|e.to_string())?;
  let tmp=parent.join(format!(".{}.tmp",path.file_name().and_then(|x|x.to_str()).unwrap_or("status.json")));
  fs::write(&tmp,serde_json::to_vec_pretty(value).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
  if path.exists(){let _=fs::remove_file(path);}fs::rename(tmp,path).map_err(|e|e.to_string())
}
fn read_value(path:&Path)->Result<Value,String>{serde_json::from_slice(&fs::read(path).map_err(|e|format!("{}: {e}",path.display()))?).map_err(|e|format!("JSON {}: {e}",path.display()))}
fn string(v:&Value,key:&str)->Result<String,String>{v.get(key).and_then(Value::as_str).filter(|x|!x.trim().is_empty()).map(str::to_string).ok_or_else(||format!("batch.json: поле {key} отсутствует"))}
fn canonical_string(path:&str)->Result<String,String>{Ok(PathBuf::from(path).canonicalize().map_err(|_|format!("Путь не найден: {path}"))?.to_string_lossy().into_owned())}
fn push_unique(items:&mut Vec<PathBuf>,path:PathBuf){if !items.iter().any(|x|x==&path){items.push(path)}}
fn push_child_manifests(items:&mut Vec<PathBuf>,dir:&Path){if let Ok(rd)=fs::read_dir(dir){for e in rd.flatten(){let p=e.path();if p.is_dir(){push_unique(items,p.join("batch.json"))}}}}
fn normalize_manifest_hint(raw:&str)->PathBuf{
  let mut s=raw.trim().trim_matches('"').to_string();
  if let Some(rest)=s.strip_prefix("file://"){s=rest.to_string()}
  s=s.replace("%20"," ");
  if let Some(rest)=s.strip_prefix("~/"){if let Some(home)=std::env::var_os("HOME"){return PathBuf::from(home).join(rest)}}
  PathBuf::from(s)
}
fn candidate_is_vyron_manifest(path:&Path)->bool{
  if !path.is_file(){return false}
  let Ok(value)=read_value(path) else{return false};
  value.get("source").and_then(Value::as_str).map(|s|s.starts_with("VYRON Production Manager")).unwrap_or(false)
}
fn handoff_source(path:&Path)->Option<PathBuf>{
  let value=read_value(path).ok()?;
  value.get("sourceManifestPath").and_then(Value::as_str).filter(|s|!s.trim().is_empty()).map(normalize_manifest_hint)
}
fn handoff_selected(path:&Path)->Vec<String>{
  read_value(path).ok().and_then(|v|v.get("selectedProjectIds").and_then(Value::as_array).cloned()).unwrap_or_default().into_iter().filter_map(|v|v.as_str().map(str::to_string)).collect()
}

#[derive(Clone,Debug,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct VyronBatchRequest{
  pub batch_id:String,
  pub manifest_path:String,
  pub requested_at:Option<String>,
  #[serde(default)] pub handoff_id:Option<String>,
  #[serde(default)] pub selected_project_ids:Vec<String>,
  #[serde(default)] pub source_manifest_path:Option<String>,
  #[serde(default)] pub schema_version:Option<u32>
}
#[derive(Clone,Debug,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct VyronBatchInfo{pub batch_id:String,pub channel_id:String,pub channel_name:String,pub project_count:usize,pub tracks_assigned:usize,pub root_path:String,pub output_dir:String,pub status_path:String,pub manifest_path:String,pub project_paths:Vec<String>}

pub(crate) fn resolve_vyron_manifest_for_request(req:&VyronBatchRequest)->Result<String,String>{
  let hint=normalize_manifest_hint(&req.manifest_path);let mut candidates=Vec::new();let mut batch_dirs=Vec::new();
  if let Some(source)=req.source_manifest_path.as_deref(){push_unique(&mut candidates,normalize_manifest_hint(source))}
  if hint.is_file(){if let Some(source)=handoff_source(&hint){push_unique(&mut candidates,source)}}
  push_unique(&mut candidates,hint.clone());
  if hint.is_dir(){push_unique(&mut candidates,hint.join("batch.json"));push_unique(&mut batch_dirs,hint.clone())}
  if let Some(parent)=hint.parent(){
    push_unique(&mut candidates,parent.join("batch.json"));push_unique(&mut batch_dirs,parent.to_path_buf());
    if let Some(grand)=parent.parent(){push_unique(&mut batch_dirs,grand.to_path_buf())}
  }

  let mut roots=Vec::new();
  if let Some(home)=std::env::var_os("HOME"){let h=PathBuf::from(home);roots.push(h.clone());roots.push(h.join("Documents"));roots.push(h.join("Downloads"));}
  if let Ok(vols)=fs::read_dir("/Volumes"){for e in vols.flatten(){let p=e.path();if p.is_dir(){roots.push(p)}}}
  for root in roots{
    for base in [
      root.join("ВАЙРОН").join("ProductionManager").join("Batches"),
      root.join("VYRON").join("ProductionManager").join("Batches"),
      root.join("ProductionManager").join("Batches"),
      root.join("Batches")
    ]{
      if base.is_dir(){push_unique(&mut batch_dirs,base.clone());push_unique(&mut batch_dirs,base.join(&req.batch_id));}
    }
  }
  for dir in batch_dirs{push_child_manifests(&mut candidates,&dir)}
  for candidate in candidates{if candidate_is_vyron_manifest(&candidate){return candidate.canonicalize().map(|p|p.to_string_lossy().into_owned()).map_err(|e|e.to_string())}}
  Err(format!("VYRON batch.json не найден для batch {}. Переданный путь: {}",req.batch_id,req.manifest_path))
}

fn request_age(path:&Path)->Duration{fs::metadata(path).ok().and_then(|m|m.modified().ok()).and_then(|t|SystemTime::now().duration_since(t).ok()).unwrap_or(Duration::ZERO)}

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
  files.sort_by_key(|p|std::cmp::Reverse(fs::metadata(p).ok().and_then(|m|m.modified().ok())));
  for p in files{
    let mut req:VyronBatchRequest=match serde_json::from_slice(&fs::read(&p).map_err(|e|e.to_string())?){Ok(v)=>v,Err(_)=>{let _=fs::remove_file(&p);continue}};
    let handoff=normalize_manifest_hint(&req.manifest_path);
    if req.selected_project_ids.is_empty()&&handoff.is_file(){req.selected_project_ids=handoff_selected(&handoff)}
    match resolve_vyron_manifest_for_request(&req){
      Ok(manifest)=>{req.source_manifest_path=Some(manifest.clone());req.manifest_path=manifest;validate_manifest(&req.manifest_path)?;let _=fs::remove_file(&p);return Ok(Some(req))}
      Err(_)=>{
        // Old failed handoffs must never block the newest selection. VYRON writes the
        // handoff/source manifest before ENDLUME polls; five seconds is only a race grace.
        if request_age(&p)>=Duration::from_secs(5){let _=fs::remove_file(&p)}
        continue
      }
    }
  }
  Ok(None)
}

#[tauri::command]
pub fn load_vyron_batch_manifest(manifest_path:String,selected_project_ids:Option<Vec<String>>)->Result<VyronBatchInfo,String>{
  let(v,manifest,root)=validate_manifest(&manifest_path)?;let projects=v.get("projects").and_then(Value::as_array).ok_or_else(||"batch.json: projects отсутствует".to_string())?;
  let declared=v.get("projectCount").and_then(Value::as_u64).unwrap_or(projects.len() as u64) as usize;if declared!=projects.len(){return Err(format!("VYRON batch: projectCount {declared}, фактически {}",projects.len()))}
  let selected=selected_project_ids.unwrap_or_default().into_iter().collect::<HashSet<_>>();
  let mut folders=HashSet::new();let mut tracks=0usize;let mut project_paths=Vec::new();
  for p in projects{
    let project_id=p.get("projectId").and_then(Value::as_str).unwrap_or("");if !selected.is_empty()&&!selected.contains(project_id){continue}
    let folder=PathBuf::from(string(p,"folderPath")?).canonicalize().map_err(|_|"VYRON project folder не найден".to_string())?;
    if !folder.starts_with(&root){return Err("Проект VYRON находится вне batch root".into())}
    if !folders.insert(folder.clone()){return Err("VYRON batch содержит повтор папки проекта".into())}
    project_paths.push(folder.to_string_lossy().into_owned());tracks+=p.get("tracks").and_then(Value::as_array).map(|x|x.len()).unwrap_or(0);
  }
  if !selected.is_empty()&&project_paths.is_empty(){return Err("Выбранные VYRON проекты не найдены в batch.json".into())}
  let output=PathBuf::from(string(&v,"outputDir")?);fs::create_dir_all(&output).map_err(|e|format!("Output dir: {e}"))?;let output=output.canonicalize().map_err(|e|e.to_string())?;if !output.starts_with(&root){return Err("Output VYRON находится вне batch root".into())}
  let status=PathBuf::from(string(&v,"statusPath")?);let status_parent=status.parent().ok_or_else(||"statusPath некорректен".to_string())?.canonicalize().map_err(|e|e.to_string())?;if status_parent!=root{return Err("statusPath VYRON находится вне batch root".into())}
  let manifest_string=manifest.to_string_lossy().into_owned();{
    let mut map=project_map().lock().map_err(|_|"VYRON project map lock".to_string())?;
    for path in &project_paths{map.insert(path.clone(),manifest_string.clone());}
  }
  Ok(VyronBatchInfo{batch_id:string(&v,"batchId")?,channel_id:string(&v,"channelId")?,channel_name:string(&v,"channelName")?,project_count:project_paths.len(),tracks_assigned:tracks,root_path:root.to_string_lossy().into_owned(),output_dir:output.to_string_lossy().into_owned(),status_path:status.to_string_lossy().into_owned(),manifest_path:manifest_string,project_paths})
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

pub fn report_if_registered(project_path:&str,render_status:&str,output_file:Option<String>,duration:Option<f64>,file_size:Option<u64>,error:Option<String>)->Result<bool,String>{
  let key=canonical_string(project_path)?;
  let manifest={project_map().lock().map_err(|_|"VYRON project map lock".to_string())?.get(&key).cloned()};
  let Some(manifest)=manifest else{return Ok(false)};
  report_vyron_render(manifest,key,render_status.to_string(),output_file,duration,file_size,error)?;Ok(true)
}
