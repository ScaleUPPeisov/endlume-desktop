use crate::{license,model::{EffectPreset,ProjectScanItem,QueueJob,RenderSettings,SubscribePreset},persistence,render};
use parking_lot::Mutex;
use serde_json::{json,Value};
use std::{collections::{HashSet,VecDeque},fs,path::PathBuf,sync::{Arc,atomic::{AtomicBool,Ordering}},time::{Instant,UNIX_EPOCH}};
use tauri::{AppHandle,Emitter,State};

const LICENSE_BLOCKED:&str="__ENDLUME_LICENSE_BLOCKED__";

#[derive(Default)]
pub struct QueueRuntime{
  pending:Mutex<VecDeque<QueueJob>>,
  active:Mutex<Option<QueueJob>>,
  finished:Mutex<VecDeque<Value>>,
  running:AtomicBool,
  cancelled:Mutex<HashSet<String>>,
  active_cancel:Mutex<Option<Arc<AtomicBool>>>,
}

impl QueueRuntime{
  fn snapshot(&self)->(Option<QueueJob>,Vec<QueueJob>){(self.active.lock().clone(),self.pending.lock().iter().cloned().collect())}
  fn terminal_snapshot(&self)->Vec<Value>{self.finished.lock().iter().cloned().collect()}
  fn remember_terminal(&self,payload:Value){
    let id=payload.get("id").and_then(Value::as_str).unwrap_or("").to_string();
    let mut done=self.finished.lock();
    if !id.is_empty(){done.retain(|v|v.get("id").and_then(Value::as_str)!=Some(id.as_str()));}
    done.push_back(payload);
    while done.len()>500{done.pop_front();}
  }
  fn clear_terminal(&self,id:&str){self.finished.lock().retain(|v|v.get("id").and_then(Value::as_str)!=Some(id));}
  fn persist(&self,app:&AppHandle){let (active,pending)=self.snapshot();let _=persistence::save_queue_state(app,active.as_ref(),&pending);}
}

fn queue_safe_name(name:&str)->String{name.chars().map(|c|if ['/', '\\', ':', '*', '?', '"', '<', '>', '|'].contains(&c){'_'}else{c}).collect()}

fn latest_result_for_job(job:&QueueJob)->(Option<String>,Option<u64>){
  let dir=PathBuf::from(&job.settings.output_dir);let prefix=format!("{} — Ready Videos",queue_safe_name(&job.project.name));
  let mut best:Option<(u128,PathBuf,u64)>=None;
  let Ok(entries)=fs::read_dir(&dir)else{return (None,None)};
  for e in entries.flatten(){
    let p=e.path();if !p.is_file(){continue}
    let ext=p.extension().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase();if ext!="mp4"&&ext!="mov"{continue}
    let name=p.file_stem().and_then(|x|x.to_str()).unwrap_or("");if !name.starts_with(&prefix){continue}
    let Ok(meta)=e.metadata()else{continue};let bytes=meta.len();
    let modified=meta.modified().ok().and_then(|t|t.duration_since(UNIX_EPOCH).ok()).map(|d|d.as_nanos()).unwrap_or(0);
    if best.as_ref().map(|x|modified>x.0).unwrap_or(true){best=Some((modified,p,bytes));}
  }
  match best{Some((_,p,b))=>(Some(p.to_string_lossy().into_owned()),Some(b)),None=>(None,None)}
}

fn done_fallback_payload(job:&QueueJob)->Value{
  let (result_path,result_bytes)=latest_result_for_job(job);
  json!({"id":job.project.id,"project":job.project,"status":"done","progress":100.0,"stage":"Готово","etaSec":0.0,"resultPath":result_path,"resultBytes":result_bytes})
}

pub(crate) fn done_payload_from_summary(job:&QueueJob,id:&str,summary:&render::RenderOutcome)->Value{
  json!({
    "id":id,
    "project":job.project,
    "status":"done",
    "progress":100.0,
    "stage":"Готово",
    "etaSec":0.0,
    "resultPath":summary.output_path,
    "resultBytes":summary.output_bytes,
    "encoder":summary.encoder,
    "finalDuration":summary.final_video_duration_seconds,
    "fastPath":summary.fast_path,
    "fastPathReason":summary.fast_path_reason,
    "audioMode":summary.audio_mode,
    "videoCodec":summary.video_codec,
    "audioCodec":summary.audio_codec
  })
}

#[tauri::command]
pub async fn enqueue_projects(app:AppHandle,runtime:State<'_,Arc<QueueRuntime>>,projects:Vec<ProjectScanItem>,settings:RenderSettings,effects:Vec<EffectPreset>,subscribes:Vec<SubscribePreset>,ambient:Option<String>)->Result<(),String>{
  license::assert_production_allowed(&app).await?;
  if settings.output_dir.trim().is_empty(){return Err("Не выбрана папка результата".into())}

  let mut effect_ids=HashSet::new();
  for effect in &effects{
    let id=effect.id.trim();
    if id.is_empty(){return Err(format!("Effects registry invalid: effect '{}' has empty ID",effect.name))}
    if !effect_ids.insert(id.to_string()){
      return Err(format!("Effects registry invalid: duplicate effect ID '{}'. Render blocked to prevent wrong-effect substitution.",id))
    }
  }

  let mut prepared=Vec::<(ProjectScanItem,Vec<EffectPreset>)>::new();
  for project in projects.into_iter().filter(|p|p.valid){
    let selected_id=project.selected_effect_id.as_deref().map(str::trim).filter(|x|!x.is_empty()).unwrap_or("__none__");
    let selected=if selected_id=="__none__"{
      Vec::new()
    }else{
      let effect=effects.iter().find(|e|e.id==selected_id).ok_or_else(||format!("Selected effect '{}' for project '{}' is not present in the effect registry",selected_id,project.name))?;
      let source=PathBuf::from(&effect.source);
      if !source.is_file(){
        return Err(format!("Selected effect '{}' ({}) for project '{}' is missing: {}",effect.name,effect.id,project.name,source.display()))
      }
      vec![effect.clone()]
    };
    prepared.push((project,selected));
  }

  {
    let active=runtime.active.lock();
    let mut q=runtime.pending.lock();
    let mut occupied=q.iter().map(|j|j.project.id.clone()).collect::<HashSet<_>>();
    if let Some(job)=active.as_ref(){occupied.insert(job.project.id.clone());}
    for (project,selected_effects) in prepared{
      if !occupied.insert(project.id.clone()){continue}
      runtime.clear_terminal(&project.id);
      q.push_back(QueueJob{project,settings:settings.clone(),effects:selected_effects,subscribes:subscribes.clone(),ambient:ambient.clone()});
    }
  }
  runtime.persist(&app);let _=app.emit("queue-changed",queue_snapshot_value(runtime.inner().as_ref()));start_worker_if_needed(app,runtime.inner().clone());Ok(())
}

fn useful_detail(raw:&str)->String{
  let lines=raw.lines().map(str::trim).filter(|x|!x.is_empty()&&!x.starts_with("frame=")&&!x.starts_with("fps=")&&!x.starts_with("out_time")&&!x.starts_with("progress=")).collect::<Vec<_>>();
  let picked=lines.iter().rev().take(6).rev().copied().collect::<Vec<_>>().join("\n");
  if picked.is_empty(){raw.trim().chars().take(700).collect()}else{picked.chars().take(1000).collect()}
}

fn friendly_error(raw:&str)->String{
  if raw==LICENSE_BLOCKED{return "Production render остановлен: лицензия ENDLUME приостановлена, отозвана или устройство заблокировано.".into()}
  let low=raw.to_lowercase();
  if low.contains("operation not permitted")||low.contains("os error 1")||low.contains("permission denied"){return "Не удалось запустить внутренний видео-движок FFmpeg.".into()}
  if low.contains("no such file")||low.contains("не найден файл")||low.contains("папка проекта не найдена"){return "Один из файлов проекта не найден. ENDLUME повторно сканирует выбранную папку, но файл всё ещё недоступен.".into()}
  if low.contains("moov atom not found")||low.contains("invalid data found")||low.contains("error opening input"){return "Один из медиафайлов повреждён или имеет неподдерживаемый формат.".into()}
  if low.contains("videotoolbox")||low.contains("hardware")||low.contains("device")&&low.contains("failed")||low.contains("encoder")&&low.contains("not found"){return "Аппаратный кодировщик не прошёл рендер. ENDLUME автоматически повторяет проект на software fallback.".into()}
  if low.contains("acrossfade")||low.contains("sample rate")||low.contains("channel layout"){return "Ошибка обработки аудиотреков. ENDLUME нормализует MP3 в 48 kHz stereo перед повтором.".into()}
  if low.contains("colorkey")||low.contains("chromakey")||low.contains("overlay"){return "Ошибка обработки Effects/Subscribe. ENDLUME не подменяет и не скрывает выбранный production-effect: проект остановлен с ошибкой.".into()}
  if raw=="__ENDLUME_CANCELLED__"{return "Остановлено пользователем".into()}
  let detail=useful_detail(raw);if detail.is_empty(){"Не удалось обработать проект.".into()}else{format!("Не удалось обработать проект. {detail}")}
}

fn save_error_log(job:&QueueJob,raw:&str)->Option<String>{
  let dir=PathBuf::from(&job.settings.output_dir).join("logs");
  if fs::create_dir_all(&dir).is_err(){return None}
  let safe=job.project.name.chars().map(|c|if ['/', '\\', ':', '*', '?', '"', '<', '>', '|'].contains(&c){'_'}else{c}).collect::<String>();
  let path=dir.join(format!("{} — error.txt",safe));
  let body=format!("ENDLUME render error\nProject: {}\nPath: {}\nVersion: {}\n\n{}\n",job.project.name,job.project.path,env!("CARGO_PKG_VERSION"),raw);
  fs::write(&path,body).ok().map(|_|path.to_string_lossy().into_owned())
}

fn start_worker_if_needed(app:AppHandle,runtime:Arc<QueueRuntime>){
  if license::production_blocked(){return}
  if runtime.running.compare_exchange(false,true,Ordering::SeqCst,Ordering::SeqCst).is_err(){return}
  tauri::async_runtime::spawn(async move{
    loop{
      if license::production_blocked(){break}
      let next={
        let mut active=runtime.active.lock();
        let mut pending=runtime.pending.lock();
        let next=pending.pop_front();
        if let Some(job)=next.as_ref(){*active=Some(job.clone());}
        next
      };
      let Some(job)=next else{break};
      runtime.persist(&app);let _=app.emit("queue-changed",queue_snapshot_value(runtime.as_ref()));
      let id=job.project.id.clone();let cancel=Arc::new(AtomicBool::new(false));*runtime.active_cancel.lock()=Some(cancel.clone());license::telemetry_render_started(&job);let job_timer=Instant::now();
      let outcome=render::render_job(&app,&job,cancel).await;*runtime.active_cancel.lock()=None;
      let cancelled=runtime.cancelled.lock().remove(&id);
      if cancelled{
        license::telemetry_render_terminal(&job,"render_cancelled",None,None,None,Some(job_timer.elapsed().as_secs_f64()));
        let payload=json!({"id":id,"project":job.project,"status":"error","progress":100.0,"stage":"Остановлено пользователем","etaSec":0.0});runtime.remember_terminal(payload.clone());let _=app.emit("render-error",payload);
      }else{
        match outcome{
          Ok(summary)=>{
            license::telemetry_render_completed(&job,&summary,job_timer.elapsed().as_secs_f64());
            let payload=done_payload_from_summary(&job,&id,&summary);
            runtime.remember_terminal(payload.clone());
            let _=app.emit("render-terminal",payload);
          }
          Err(error) if error==LICENSE_BLOCKED||license::production_blocked()=>{
            license::telemetry_render_terminal(&job,"render_cancelled",None,None,Some("license_blocked"),Some(job_timer.elapsed().as_secs_f64()));
            runtime.pending.lock().push_front(job.clone());let _=app.emit("render-warning",json!({"id":id,"message":"Лицензия изменена владельцем. Текущий render остановлен, очередь удерживается до восстановления доступа."}));
            *runtime.active.lock()=None;runtime.persist(&app);let _=app.emit("queue-changed",queue_snapshot_value(runtime.as_ref()));break
          }
          Err(error)=>{
            license::telemetry_render_terminal(&job,"render_failed",None,None,Some(&error),Some(job_timer.elapsed().as_secs_f64()));
            let log_path=save_error_log(&job,&error);let friendly=friendly_error(&error);let detail=useful_detail(&error);
            let payload=json!({"id":id,"project":job.project,"status":"error","progress":100.0,"stage":format!("Ошибка: {friendly}"),"error":friendly,"errorDetail":detail,"logPath":log_path,"etaSec":0.0});runtime.remember_terminal(payload.clone());let _=app.emit("render-error",payload);
          }
        }
      }
      *runtime.active.lock()=None;runtime.persist(&app);let _=app.emit("queue-changed",queue_snapshot_value(runtime.as_ref()));
    }
    runtime.running.store(false,Ordering::SeqCst);runtime.persist(&app);let _=app.emit("queue-idle",json!({"idle":true,"licenseHold":license::production_blocked()}));if !runtime.pending.lock().is_empty()&&!license::production_blocked(){start_worker_if_needed(app,runtime)}
  });
}

fn queue_snapshot_value(runtime:&QueueRuntime)->Value{let (active,pending)=runtime.snapshot();let finished=runtime.terminal_snapshot();json!({"active":active,"pending":pending,"finished":finished,"running":runtime.running.load(Ordering::SeqCst),"licenseHold":license::production_blocked()})}
#[tauri::command] pub fn queue_snapshot(runtime:State<'_,Arc<QueueRuntime>>)->Value{queue_snapshot_value(runtime.inner().as_ref())}

#[tauri::command]
pub fn cancel_project(app:AppHandle,runtime:State<'_,Arc<QueueRuntime>>,id:String)->Result<(),String>{
  let is_active=runtime.active.lock().as_ref().map(|j|j.project.id.as_str())==Some(id.as_str());runtime.pending.lock().retain(|j|j.project.id!=id);
  if is_active{runtime.cancelled.lock().insert(id.clone());if let Some(flag)=runtime.active_cancel.lock().as_ref(){flag.store(true,Ordering::SeqCst);}}
  runtime.persist(&app);let _=app.emit("queue-changed",queue_snapshot_value(runtime.inner().as_ref()));Ok(())
}

#[tauri::command]
pub fn reorder_queue(app:AppHandle,runtime:State<'_,Arc<QueueRuntime>>,ids:Vec<String>)->Result<(),String>{
  let mut q=runtime.pending.lock();let mut all:Vec<QueueJob>=q.drain(..).collect();let mut reordered=VecDeque::new();
  for id in ids{if let Some(pos)=all.iter().position(|j|j.project.id==id){reordered.push_back(all.remove(pos));}}
  for job in all{reordered.push_back(job)}*q=reordered;drop(q);runtime.persist(&app);let _=app.emit("queue-changed",queue_snapshot_value(runtime.inner().as_ref()));Ok(())
}

#[tauri::command]
pub async fn resume_recovery(app:AppHandle,runtime:State<'_,Arc<QueueRuntime>>)->Result<(),String>{
  license::assert_production_allowed(&app).await?;
  let value=persistence::read_value(&app,"recovery.json");if !value.get("interrupted").and_then(Value::as_bool).unwrap_or(false){return Ok(())}
  let mut jobs=Vec::new();if let Some(active)=value.get("active").filter(|v|!v.is_null()){if let Ok(job)=serde_json::from_value::<QueueJob>(active.clone()){jobs.push(job)}}
  if let Some(pending)=value.get("pending").and_then(Value::as_array){for v in pending{if let Ok(job)=serde_json::from_value::<QueueJob>(v.clone()){jobs.push(job)}}}
  let mut recovered_projects=Vec::new();
  {
    let active=runtime.active.lock();
    let mut q=runtime.pending.lock();
    let mut occupied=q.iter().map(|j|j.project.id.clone()).collect::<HashSet<_>>();
    if let Some(job)=active.as_ref(){occupied.insert(job.project.id.clone());}
    for job in jobs{
      if !occupied.insert(job.project.id.clone()){continue}
      runtime.clear_terminal(&job.project.id);
      recovered_projects.push(job.project.clone());
      q.push_back(job);
    }
  }
  let _=app.emit("queue-recovered",json!({"projects":recovered_projects}));let _=persistence::write_value(&app,"recovery.json",&json!({"interrupted":false}));runtime.persist(&app);start_worker_if_needed(app,runtime.inner().clone());Ok(())
}

#[tauri::command]
pub async fn resume_license_queue(app:AppHandle,runtime:State<'_,Arc<QueueRuntime>>)->Result<(),String>{
  license::assert_production_allowed(&app).await?;start_worker_if_needed(app,runtime.inner().clone());Ok(())
}
