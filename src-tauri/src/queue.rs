use crate::{model::{EffectPreset,ProjectScanItem,QueueJob,RenderSettings,SubscribePreset},persistence,render};
use parking_lot::Mutex;
use serde_json::{json,Value};
use std::{collections::{HashSet,VecDeque},fs,path::PathBuf,sync::{Arc,atomic::{AtomicBool,Ordering}}};
use tauri::{AppHandle,Emitter,State};

#[derive(Default)]
pub struct QueueRuntime{
  pending:Mutex<VecDeque<QueueJob>>,
  active:Mutex<Option<QueueJob>>,
  running:AtomicBool,
  cancelled:Mutex<HashSet<String>>,
  active_cancel:Mutex<Option<Arc<AtomicBool>>>,
}

impl QueueRuntime{
  fn snapshot(&self)->(Option<QueueJob>,Vec<QueueJob>){(self.active.lock().clone(),self.pending.lock().iter().cloned().collect())}
  fn persist(&self,app:&AppHandle){let (active,pending)=self.snapshot();let _=persistence::save_queue_state(app,active.as_ref(),&pending);}
}

#[tauri::command]
pub async fn enqueue_projects(app:AppHandle,runtime:State<'_,Arc<QueueRuntime>>,projects:Vec<ProjectScanItem>,settings:RenderSettings,effects:Vec<EffectPreset>,subscribes:Vec<SubscribePreset>,ambient:Option<String>)->Result<(),String>{
  if settings.output_dir.trim().is_empty(){return Err("Не выбрана папка результата".into())}
  {let mut q=runtime.pending.lock();for project in projects.into_iter().filter(|p|p.valid){q.push_back(QueueJob{project,settings:settings.clone(),effects:effects.clone(),subscribes:subscribes.clone(),ambient:ambient.clone()});}}
  runtime.persist(&app);let _=app.emit("queue-changed",queue_snapshot_value(runtime.inner().as_ref()));start_worker_if_needed(app,runtime.inner().clone());Ok(())
}

fn useful_detail(raw:&str)->String{
  let lines=raw.lines().map(str::trim).filter(|x|!x.is_empty()&&!x.starts_with("frame=")&&!x.starts_with("fps=")&&!x.starts_with("out_time")&&!x.starts_with("progress=")).collect::<Vec<_>>();
  let picked=lines.iter().rev().take(6).rev().copied().collect::<Vec<_>>().join("\n");
  if picked.is_empty(){raw.trim().chars().take(700).collect()}else{picked.chars().take(1000).collect()}
}

fn friendly_error(raw:&str)->String{
  let low=raw.to_lowercase();
  if low.contains("no such file")||low.contains("не найден файл")||low.contains("папка проекта не найдена"){return "Один из файлов проекта не найден. ENDLUME повторно сканирует выбранную папку, но файл всё ещё недоступен.".into()}
  if low.contains("moov atom not found")||low.contains("invalid data found")||low.contains("error opening input"){return "Один из медиафайлов повреждён или имеет неподдерживаемый формат.".into()}
  if low.contains("videotoolbox")||low.contains("hardware")||low.contains("device")&&low.contains("failed")||low.contains("encoder")&&low.contains("not found"){return "Аппаратный кодировщик не прошёл рендер. ENDLUME автоматически повторяет проект на software fallback.".into()}
  if low.contains("acrossfade")||low.contains("sample rate")||low.contains("channel layout"){return "Ошибка обработки аудиотреков. ENDLUME нормализует MP3 в 48 kHz stereo перед повтором.".into()}
  if low.contains("colorkey")||low.contains("chromakey")||low.contains("overlay"){return "Ошибка обработки Effects/Subscribe. Проблемный overlay должен быть пропущен без остановки основного видео.".into()}
  if raw=="__ENDLUME_CANCELLED__"{return "Остановлено пользователем".into()}
  let detail=useful_detail(raw);if detail.is_empty(){"Не удалось обработать проект.".into()}else{format!("Не удалось обработать проект. {detail}")}
}

fn save_error_log(job:&QueueJob,raw:&str)->Option<String>{
  let dir=PathBuf::from(&job.settings.output_dir).join("logs");
  if fs::create_dir_all(&dir).is_err(){return None}
  let safe=job.project.name.chars().map(|c|if ['/', '\\', ':', '*', '?', '"', '<', '>', '|'].contains(&c){'_'}else{c}).collect::<String>();
  let path=dir.join(format!("{} — error.txt",safe));
  let body=format!("ENDLUME render error\nProject: {}\nPath: {}\nVersion: alpha.8.19\n\n{}\n",job.project.name,job.project.path,raw);
  fs::write(&path,body).ok().map(|_|path.to_string_lossy().into_owned())
}

fn start_worker_if_needed(app:AppHandle,runtime:Arc<QueueRuntime>){
  if runtime.running.compare_exchange(false,true,Ordering::SeqCst,Ordering::SeqCst).is_err(){return}
  tauri::async_runtime::spawn(async move{
    loop{
      let next={runtime.pending.lock().pop_front()};let Some(job)=next else{break};*runtime.active.lock()=Some(job.clone());runtime.persist(&app);let _=app.emit("queue-changed",queue_snapshot_value(runtime.as_ref()));
      let id=job.project.id.clone();let cancel=Arc::new(AtomicBool::new(false));*runtime.active_cancel.lock()=Some(cancel.clone());let outcome=render::render_job(&app,&job,cancel).await;*runtime.active_cancel.lock()=None;
      if runtime.cancelled.lock().remove(&id){let _=app.emit("render-error",json!({"id":id,"status":"error","progress":100.0,"stage":"Остановлено пользователем"}));}
      else if let Err(error)=outcome{
        let log_path=save_error_log(&job,&error);let friendly=friendly_error(&error);let detail=useful_detail(&error);
        let _=app.emit("render-error",json!({"id":id,"status":"error","progress":100.0,"stage":format!("Ошибка: {friendly}"),"error":friendly,"errorDetail":detail,"logPath":log_path}));
      }
      *runtime.active.lock()=None;runtime.persist(&app);let _=app.emit("queue-changed",queue_snapshot_value(runtime.as_ref()));
    }
    runtime.running.store(false,Ordering::SeqCst);runtime.persist(&app);let _=app.emit("queue-idle",json!({"idle":true}));if !runtime.pending.lock().is_empty(){start_worker_if_needed(app,runtime)}
  });
}

fn queue_snapshot_value(runtime:&QueueRuntime)->Value{let (active,pending)=runtime.snapshot();json!({"active":active,"pending":pending,"running":runtime.running.load(Ordering::SeqCst)})}
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
pub fn resume_recovery(app:AppHandle,runtime:State<'_,Arc<QueueRuntime>>)->Result<(),String>{
  let value=persistence::read_value(&app,"recovery.json");if !value.get("interrupted").and_then(Value::as_bool).unwrap_or(false){return Ok(())}
  let mut jobs=Vec::new();if let Some(active)=value.get("active").filter(|v|!v.is_null()){if let Ok(job)=serde_json::from_value::<QueueJob>(active.clone()){jobs.push(job)}}
  if let Some(pending)=value.get("pending").and_then(Value::as_array){for v in pending{if let Ok(job)=serde_json::from_value::<QueueJob>(v.clone()){jobs.push(job)}}}
  let recovered_projects=jobs.iter().map(|j|j.project.clone()).collect::<Vec<_>>();{let mut q=runtime.pending.lock();for job in jobs{q.push_back(job)}}
  let _=app.emit("queue-recovered",json!({"projects":recovered_projects}));let _=persistence::write_value(&app,"recovery.json",&json!({"interrupted":false}));runtime.persist(&app);start_worker_if_needed(app,runtime.inner().clone());Ok(())
}
