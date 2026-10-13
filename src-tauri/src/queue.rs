use crate::{license,model::{BackgroundMusicSettings,EffectPreset,ProjectScanItem,QueueJob,RenderSettings,SubscribePreset},persistence,render};
use parking_lot::Mutex;
use serde_json::{json,Value};
use std::{collections::{HashSet,VecDeque},fs,path::{Path,PathBuf},sync::{Arc,atomic::{AtomicBool,Ordering}},time::{Instant,UNIX_EPOCH}};
use tauri::{AppHandle,Emitter,State};

const LICENSE_BLOCKED:&str="__ENDLUME_LICENSE_BLOCKED__";
const NO_EFFECT_SELECTION:&str="__none__";

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


// ENDLUME_VYRON_RENDER_DESTINATION_ROUTING_HOTFIX
// VYRON project metadata owns the final destination. ProductionManager/Batches
// remains orchestration/workspace only and is never accepted as final output.
#[derive(Clone,Debug)]
pub(crate) struct VyronRenderRoute{
  vyron_root:String,
  channel:String,
  project_directory:String,
  batch_directory:String,
  final_render_directory:String,
}

fn is_vyron_managed(project:&ProjectScanItem)->bool{
  project.output_source.as_deref().map(str::trim).map(|s|s.eq_ignore_ascii_case("vyron")).unwrap_or(false)
    || project.vyron_manifest_path.as_deref().map(str::trim).map(|s|!s.is_empty()).unwrap_or(false)
    || project.vyron_channel_name.as_deref().map(str::trim).map(|s|!s.is_empty()).unwrap_or(false)
}

fn canonical_existing(path:&Path,label:&str)->Result<PathBuf,String>{
  path.canonicalize().map_err(|e|format!("VYRON routing: {label} недоступен: {} ({e})",path.display()))
}

fn resolve_vyron_render_route(project:&ProjectScanItem)->Result<Option<VyronRenderRoute>,String>{
  if !is_vyron_managed(project){return Ok(None)}
  let channel=project.vyron_channel_name.as_deref().map(str::trim).filter(|s|!s.is_empty()).ok_or_else(||format!("VYRON routing: project '{}' не содержит persisted channel identity",project.name))?;
  if channel=="."||channel==".."||channel.chars().any(|c|c=='/'||c=='\\'){
    return Err(format!("VYRON routing: некорректное channel name '{}' для project '{}'",channel,project.name))
  }

  let project_dir=canonical_existing(Path::new(&project.path),"PROJECT DIRECTORY")?;
  let production_manager=project_dir.ancestors().find(|p|p.file_name().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("ProductionManager")).unwrap_or(false))
    .ok_or_else(||format!("VYRON routing: PROJECT DIRECTORY '{}' не находится внутри ProductionManager",project_dir.display()))?;
  let vyron_root=production_manager.parent().ok_or_else(||format!("VYRON routing: не удалось определить VYRON ROOT для '{}'",project.name))?.to_path_buf();
  let vyron_root=canonical_existing(&vyron_root,"VYRON ROOT")?;
  let batches_root=canonical_existing(&vyron_root.join("ProductionManager").join("Batches"),"ProductionManager/Batches")?;

  let batch_dir=project.vyron_manifest_path.as_deref().map(str::trim).filter(|s|!s.is_empty())
    .and_then(|s|Path::new(s).parent().map(Path::to_path_buf))
    .or_else(||project_dir.parent().map(Path::to_path_buf))
    .ok_or_else(||format!("VYRON routing: не удалось определить BATCH DIRECTORY для '{}'",project.name))?;
  let batch_dir=canonical_existing(&batch_dir,"BATCH DIRECTORY")?;

  let expected=vyron_root.join("Render").join(channel);
  fs::create_dir_all(&expected).map_err(|e|format!("VYRON routing: не удалось создать FINAL RENDER DIRECTORY '{}': {e}",expected.display()))?;
  let expected=canonical_existing(&expected,"FINAL RENDER DIRECTORY")?;

  let resolved=if let Some(raw)=project.output_dir.as_deref().map(str::trim).filter(|s|!s.is_empty()){
    let supplied=PathBuf::from(raw);
    fs::create_dir_all(&supplied).map_err(|e|format!("VYRON routing: persisted outputDirectory '{}' недоступен: {e}",supplied.display()))?;
    canonical_existing(&supplied,"persisted outputDirectory")?
  }else{
    // Deterministic recovery is allowed only when persisted output metadata is
    // absent: VYRON ROOT + Render + persisted channel identity.
    expected.clone()
  };

  if resolved.starts_with(&batches_root){
    return Err(format!("VYRON routing blocked BATCH_OUTPUT_LEAK: project='{}' final='{}' batches='{}'",project.name,resolved.display(),batches_root.display()))
  }
  if resolved!=expected{
    return Err(format!("VYRON routing destination mismatch for project '{}': persisted='{}' expected='{}'",project.name,resolved.display(),expected.display()))
  }

  Ok(Some(VyronRenderRoute{
    vyron_root:vyron_root.to_string_lossy().into_owned(),
    channel:channel.to_string(),
    project_directory:project_dir.to_string_lossy().into_owned(),
    batch_directory:batch_dir.to_string_lossy().into_owned(),
    final_render_directory:expected.to_string_lossy().into_owned(),
  }))
}

pub(crate) fn enforce_render_destination(job:&mut QueueJob)->Result<bool,String>{
  let Some(route)=resolve_vyron_render_route(&job.project)? else{return Ok(false)};
  job.settings.output_dir=route.final_render_directory.clone();
  job.project.output_dir=Some(route.final_render_directory);
  job.project.output_source=Some("vyron".into());
  Ok(true)
}

pub(crate) fn log_render_route(job:&QueueJob){
  let Ok(Some(route))=resolve_vyron_render_route(&job.project) else{return};
  eprintln!("VYRON ROOT={}",route.vyron_root);
  eprintln!("CHANNEL={}",route.channel);
  eprintln!("PROJECT DIRECTORY={}",route.project_directory);
  eprintln!("BATCH DIRECTORY={}",route.batch_directory);
  eprintln!("FINAL RENDER DIRECTORY={}",route.final_render_directory);
}

pub(crate) fn log_final_output(job:&QueueJob,output_file:&str){
  if is_vyron_managed(&job.project){eprintln!("FINAL OUTPUT FILE={output_file}")}
}

fn normalized_project_effect_ids(project:&ProjectScanItem)->Vec<String>{
  let source=if !project.selected_effect_ids.is_empty(){
    project.selected_effect_ids.clone()
  }else{
    project.selected_effect_id.as_deref().map(str::trim).filter(|id|!id.is_empty()).map(|id|vec![id.to_string()]).unwrap_or_default()
  };
  let mut seen=HashSet::new();
  source.into_iter().map(|id|id.trim().to_string()).filter(|id|!id.is_empty()&&seen.insert(id.clone())).collect()
}

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
pub async fn enqueue_projects(app:AppHandle,runtime:State<'_,Arc<QueueRuntime>>,projects:Vec<ProjectScanItem>,settings:RenderSettings,effects:Vec<EffectPreset>,subscribes:Vec<SubscribePreset>,ambient:Option<String>,ambient_settings:BackgroundMusicSettings)->Result<(),String>{
  license::assert_production_allowed(&app).await?;
  if settings.output_dir.trim().is_empty()&&projects.iter().filter(|p|p.valid).any(|p|!is_vyron_managed(p)){return Err("Не выбрана папка результата".into())}

  let mut effect_ids=HashSet::new();
  for effect in &effects{
    let id=effect.id.trim();
    if id.is_empty(){return Err(format!("Effects registry invalid: effect '{}' has empty ID",effect.name))}
    if !effect_ids.insert(id.to_string()){
      return Err(format!("Effects registry invalid: duplicate effect ID '{}'. Render blocked to prevent wrong-effect substitution.",id))
    }
  }

  let mut prepared=Vec::<QueueJob>::new();
  for mut project in projects.into_iter().filter(|p|p.valid){
    let selected_ids=normalized_project_effect_ids(&project);
    let selected=if selected_ids.is_empty(){
      if effects.is_empty(){Vec::new()}else{return Err(format!("Project '{}' has Effects available but no explicit selectedEffectIds. Choose one or more effects or «Без эффекта» before rendering.",project.name))}
    }else if selected_ids.iter().any(|id|id==NO_EFFECT_SELECTION){
      if selected_ids.len()!=1{return Err(format!("Project '{}' mixes «Без эффекта» with real Effects. Choose one mode only.",project.name))}
      Vec::new()
    }else{
      let mut resolved=Vec::with_capacity(selected_ids.len());
      for selected_id in &selected_ids{
        let effect=effects.iter().find(|e|e.id==*selected_id).ok_or_else(||format!("Selected effect '{}' for project '{}' is not present in the effect registry",selected_id,project.name))?;
        if !effect.enabled||effect.usage_mode.as_deref()==Some("off"){
          return Err(format!("Selected effect '{}' ({}) for project '{}' is disabled. Re-enable it or choose another effect before rendering.",effect.name,effect.id,project.name))
        }
        let source=PathBuf::from(&effect.source);
        if !source.is_file(){
          return Err(format!("Selected effect '{}' ({}) for project '{}' is missing: {}",effect.name,effect.id,project.name,source.display()))
        }
        resolved.push(effect.clone());
      }
      resolved
    };
    project.selected_effect_ids=if selected.is_empty(){vec![NO_EFFECT_SELECTION.into()]}else{selected.iter().map(|effect|effect.id.clone()).collect()};
    project.selected_effect_id=if project.selected_effect_ids.len()==1{Some(project.selected_effect_ids[0].clone())}else{None};
    let mut job=QueueJob{project,settings:settings.clone(),effects:selected,subscribes:subscribes.clone(),ambient:ambient.clone(),ambient_settings:ambient_settings.clone()};
    enforce_render_destination(&mut job)?;
    prepared.push(job);
  }

  {
    let active=runtime.active.lock();
    let mut q=runtime.pending.lock();
    let mut occupied=q.iter().map(|j|j.project.id.clone()).collect::<HashSet<_>>();
    if let Some(job)=active.as_ref(){occupied.insert(job.project.id.clone());}
    for job in prepared{
      if !occupied.insert(job.project.id.clone()){continue}
      runtime.clear_terminal(&job.project.id);
      q.push_back(job);
    }
  }
  runtime.persist(&app);let _=app.emit("queue-changed",queue_snapshot_value(runtime.inner().as_ref()));start_worker_if_needed(app,runtime.inner().clone());Ok(())
}

fn validate_recovered_effect_contract(job:&mut QueueJob)->Result<(),String>{
  let mut selected=normalized_project_effect_ids(&job.project);
  if selected.is_empty()&&!job.effects.is_empty(){
    selected=job.effects.iter().map(|effect|effect.id.trim().to_string()).filter(|id|!id.is_empty()).collect();
    selected.dedup();
    job.project.selected_effect_ids=selected.clone();
    job.project.selected_effect_id=if selected.len()==1{Some(selected[0].clone())}else{None};
  }
  if selected.is_empty(){
    job.project.selected_effect_ids=vec![NO_EFFECT_SELECTION.into()];
    job.project.selected_effect_id=Some(NO_EFFECT_SELECTION.into());
    return if job.effects.is_empty(){Ok(())}else{Err(format!("recovery содержит {} effect preset(s), но не содержит сохранённых effect IDs",job.effects.len()))};
  }
  if selected.iter().any(|id|id==NO_EFFECT_SELECTION){
    if selected.len()!=1{return Err("recovery смешивает «Без эффекта» с реальными Effects".into())}
    if !job.effects.is_empty(){return Err("recovery содержит Effects при явном выборе «Без эффекта»".into())}
    job.project.selected_effect_ids=vec![NO_EFFECT_SELECTION.into()];job.project.selected_effect_id=Some(NO_EFFECT_SELECTION.into());return Ok(())
  }
  let actual=job.effects.iter().map(|effect|effect.id.trim().to_string()).collect::<Vec<_>>();
  if actual!=selected{return Err(format!("recovery effect IDs {:?} не совпадают с сохранёнными selectedEffectIds {:?}",actual,selected))}
  for effect in &job.effects{
    if !effect.enabled||effect.usage_mode.as_deref()==Some("off"){return Err(format!("recovery effect '{}' ({}) выключен",effect.name,effect.id))}
    let source=PathBuf::from(&effect.source);
    if !source.is_file(){return Err(format!("recovery effect '{}' ({}) не найден: {}",effect.name,effect.id,source.display()))}
  }
  job.project.selected_effect_ids=selected.clone();job.project.selected_effect_id=if selected.len()==1{Some(selected[0].clone())}else{None};Ok(())
}

fn validate_recovered_job(job:&mut QueueJob)->Result<(),String>{
  validate_recovered_effect_contract(job)?;
  enforce_render_destination(job).map(|_|())
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
      let outcome=crate::render_with_phase3_fast(&app,&job,cancel).await;*runtime.active_cancel.lock()=None;
      let cancelled=runtime.cancelled.lock().remove(&id);
      if cancelled{
        license::telemetry_render_terminal(&job,"render_cancelled",None,None,None,Some(job_timer.elapsed().as_secs_f64()));
        let payload=json!({"id":id,"project":job.project,"status":"error","progress":100.0,"stage":"Остановлено пользователем","etaSec":0.0});runtime.remember_terminal(payload.clone());let _=app.emit("render-error",payload);
      }else{
        match outcome{
          Ok(summary)=>{license::telemetry_render_completed(&job,&summary,job_timer.elapsed().as_secs_f64());let payload=done_payload_from_summary(&job,&id,&summary);runtime.remember_terminal(payload.clone());let _=app.emit("render-terminal",payload);}
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
  let mut jobs=Vec::new();let mut blocked=Vec::<String>::new();
  if let Some(active)=value.get("active").filter(|v|!v.is_null()){
    if let Ok(mut job)=serde_json::from_value::<QueueJob>(active.clone()){
      match validate_recovered_job(&mut job){Ok(())=>jobs.push(job),Err(reason)=>blocked.push(format!("{}: {}",job.project.name,reason))}
    }
  }
  if let Some(pending)=value.get("pending").and_then(Value::as_array){
    for v in pending{
      if let Ok(mut job)=serde_json::from_value::<QueueJob>(v.clone()){
        match validate_recovered_job(&mut job){Ok(())=>jobs.push(job),Err(reason)=>blocked.push(format!("{}: {}",job.project.name,reason))}
      }
    }
  }
  let mut recovered_projects=Vec::new();
  {
    let active=runtime.active.lock();let mut q=runtime.pending.lock();let mut occupied=q.iter().map(|j|j.project.id.clone()).collect::<HashSet<_>>();
    if let Some(job)=active.as_ref(){occupied.insert(job.project.id.clone());}
    for job in jobs{if !occupied.insert(job.project.id.clone()){continue}runtime.clear_terminal(&job.project.id);recovered_projects.push(job.project.clone());q.push_back(job);}
  }
  if !blocked.is_empty(){
    let shown=blocked.iter().take(8).cloned().collect::<Vec<_>>().join("\n");let more=blocked.len().saturating_sub(8);let suffix=if more>0{format!("\n…и ещё {more}")}else{String::new()};
    let _=app.emit("render-warning",json!({"id":"recovery-effect-contract","message":format!("ENDLUME не восстановил {} legacy job(s) с неоднозначным Effects state. Добавьте эти проекты в очередь заново и явно выберите эффект или «Без эффекта».\n{}{}",blocked.len(),shown,suffix)}));
  }
  let _=app.emit("queue-recovered",json!({"projects":recovered_projects}));let _=persistence::write_value(&app,"recovery.json",&json!({"interrupted":false}));runtime.persist(&app);start_worker_if_needed(app,runtime.inner().clone());Ok(())
}

#[tauri::command]
pub async fn resume_license_queue(app:AppHandle,runtime:State<'_,Arc<QueueRuntime>>)->Result<(),String>{
  license::assert_production_allowed(&app).await?;start_worker_if_needed(app,runtime.inner().clone());Ok(())
}


#[cfg(test)]
mod render_destination_routing_tests{
  use super::*;
  use uuid::Uuid;

  fn fixture(channel:&str,explicit_output:bool)->(PathBuf,QueueJob,PathBuf,PathBuf){
    let base=std::env::temp_dir().join(format!("endlume-routing-{}",Uuid::new_v4()));
    let vyron=base.join("VYRON");
    let batch=vyron.join("ProductionManager").join("Batches").join("batch-001");
    let project_dir=batch.join("project-001");
    let expected=vyron.join("Render").join(channel);
    fs::create_dir_all(&project_dir).unwrap();
    fs::create_dir_all(&expected).unwrap();
    let project=ProjectScanItem{
      id:"routing-test".into(),name:"routing-test".into(),path:project_dir.to_string_lossy().into_owned(),media:vec![],audio:vec![],valid:true,error:None,anchors:None,
      selected_effect_id:None,selected_effect_ids:vec![],
      output_dir:if explicit_output{Some(expected.to_string_lossy().into_owned())}else{None},
      output_source:Some("vyron".into()),
      vyron_manifest_path:Some(batch.join("batch.json").to_string_lossy().into_owned()),
      vyron_channel_name:Some(channel.into()),
    };
    let settings=RenderSettings{width:1920,height:1080,fps:60,codec:"h265".into(),bitrate_mbps:30.0,duration_hours:1.0,duration_mode:"auto".into(),loop_mode:"image".into(),crossfade_sec:0.0,normalize_lufs:false,output_dir:project_dir.to_string_lossy().into_owned(),preset:"fast".into(),encoder_preference:"auto".into()};
    let job=QueueJob{project,settings,effects:vec![],subscribes:vec![],ambient:None,ambient_settings:BackgroundMusicSettings::default()};
    (base,job,expected,project_dir)
  }

  #[test]
  fn vyron_explicit_project_output_overrides_poisoned_batch_settings(){
    let(base,mut job,expected,project_dir)=fixture("Afterglow Highway",true);
    assert_eq!(PathBuf::from(&job.settings.output_dir),project_dir);
    assert!(enforce_render_destination(&mut job).unwrap());
    assert_eq!(PathBuf::from(&job.settings.output_dir).canonicalize().unwrap(),expected.canonicalize().unwrap());
    assert_eq!(PathBuf::from(job.project.output_dir.as_deref().unwrap()).canonicalize().unwrap(),expected.canonicalize().unwrap());
    fs::remove_dir_all(base).unwrap();
  }

  #[test]
  fn vyron_missing_output_metadata_recovers_root_render_channel(){
    let(base,mut job,expected,_)=fixture("Aether Riff",false);
    assert!(enforce_render_destination(&mut job).unwrap());
    assert_eq!(PathBuf::from(&job.settings.output_dir).canonicalize().unwrap(),expected.canonicalize().unwrap());
    assert_eq!(PathBuf::from(job.project.output_dir.as_deref().unwrap()).canonicalize().unwrap(),expected.canonicalize().unwrap());
    fs::remove_dir_all(base).unwrap();
  }

  #[test]
  fn vyron_recovery_repairs_legacy_serialized_batch_destination(){
    let(base,job,expected,project_dir)=fixture("Aegean Afterglow",true);
    let bytes=serde_json::to_vec(&job).unwrap();
    let mut restored:QueueJob=serde_json::from_slice(&bytes).unwrap();
    restored.settings.output_dir=project_dir.to_string_lossy().into_owned();
    assert!(enforce_render_destination(&mut restored).unwrap());
    assert_eq!(PathBuf::from(&restored.settings.output_dir).canonicalize().unwrap(),expected.canonicalize().unwrap());
    fs::remove_dir_all(base).unwrap();
  }

  #[test]
  fn vyron_batch_directory_is_rejected_as_final_output(){
    let(base,mut job,_expected,project_dir)=fixture("After Dark Voice",true);
    job.project.output_dir=Some(project_dir.to_string_lossy().into_owned());
    let err=enforce_render_destination(&mut job).unwrap_err();
    assert!(err.contains("BATCH_OUTPUT_LEAK"),"{err}");
    fs::remove_dir_all(base).unwrap();
  }

  #[test]
  fn standalone_endlume_keeps_existing_output_behavior(){
    let base=std::env::temp_dir().join(format!("endlume-standalone-routing-{}",Uuid::new_v4()));
    let project_dir=base.join("project");let output=base.join("standalone-output");fs::create_dir_all(&project_dir).unwrap();fs::create_dir_all(&output).unwrap();
    let project=ProjectScanItem{id:"standalone".into(),name:"standalone".into(),path:project_dir.to_string_lossy().into_owned(),media:vec![],audio:vec![],valid:true,error:None,anchors:None,selected_effect_id:None,selected_effect_ids:vec![],output_dir:None,output_source:None,vyron_manifest_path:None,vyron_channel_name:None};
    let settings=RenderSettings{width:1920,height:1080,fps:60,codec:"h265".into(),bitrate_mbps:30.0,duration_hours:1.0,duration_mode:"auto".into(),loop_mode:"image".into(),crossfade_sec:0.0,normalize_lufs:false,output_dir:output.to_string_lossy().into_owned(),preset:"fast".into(),encoder_preference:"auto".into()};
    let mut job=QueueJob{project,settings,effects:vec![],subscribes:vec![],ambient:None,ambient_settings:BackgroundMusicSettings::default()};
    assert!(!enforce_render_destination(&mut job).unwrap());
    assert_eq!(PathBuf::from(&job.settings.output_dir).canonicalize().unwrap(),output.canonicalize().unwrap());
    fs::remove_dir_all(base).unwrap();
  }
}
