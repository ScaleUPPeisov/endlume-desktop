from pathlib import Path
import re

p = Path('src-tauri/src/render.rs')
text = p.read_text(encoding='utf-8')

# Access to app cache/video directories.
text = text.replace('use tauri::{AppHandle,Emitter};', 'use tauri::{AppHandle,Emitter,Manager};')

helper_marker = 'fn emit_timing(app:&AppHandle,id:&str,key:&str,sec:f64){let _=app.emit("engine-timing",json!({"id":id,"key":key,"seconds":sec}));}\n'
helpers = r'''

const AUDIO_EXT:&[&str]=&["mp3","wav","m4a","aac","flac","ogg","opus","aif","aiff"];
fn is_audio(path:&Path)->bool{path.extension().and_then(|x|x.to_str()).map(|x|AUDIO_EXT.contains(&x.to_ascii_lowercase().as_str())).unwrap_or(false)}
fn software_encoder(s:&RenderSettings)->String{if s.codec.eq_ignore_ascii_case("h265"){"libx265".into()}else{"libx264".into()}}
fn emit_warning(app:&AppHandle,id:&str,message:&str){let _=app.emit("render-warning",json!({"id":id,"message":message}));}

fn writable_dir(path:&Path)->bool{
  if std::fs::create_dir_all(path).is_err(){return false}
  let probe=path.join(format!(".endlume-write-test-{}",uuid::Uuid::new_v4()));
  match std::fs::write(&probe,b"ok"){Ok(_)=>{let _=std::fs::remove_file(probe);true},Err(_)=>false}
}

fn resolve_output_dir(app:&AppHandle,requested:&Path)->Result<PathBuf,String>{
  if !requested.as_os_str().is_empty()&&writable_dir(requested){return Ok(requested.to_path_buf())}
  let fallback=app.path().video_dir().map_err(|e|format!("Не удалось определить папку Movies: {e}"))?.join("ENDLUME Studio");
  if writable_dir(&fallback){Ok(fallback)}else{Err("ENDLUME не может записать ни в выбранную папку, ни в Movies/ENDLUME Studio".into())}
}

fn render_work_dir(app:&AppHandle,job_id:&str,attempt:u32)->Result<PathBuf,String>{
  let root=app.path().app_cache_dir().map_err(|e|format!("Не удалось открыть кэш ENDLUME: {e}"))?.join("render-work");
  std::fs::create_dir_all(&root).map_err(|e|format!("Не удалось создать render-work: {e}"))?;
  let safe=safe_name(job_id);
  let dir=root.join(format!("{}-{}-{}",safe,attempt,uuid::Uuid::new_v4()));
  std::fs::create_dir_all(&dir).map_err(|e|format!("Не удалось создать рабочую папку рендера: {e}"))?;
  Ok(dir)
}

fn refresh_project_paths(job:&mut QueueJob){
  let root=PathBuf::from(&job.project.path);
  if root.is_dir(){
    let media_missing=job.project.media.is_empty()||job.project.media.iter().any(|p|!Path::new(p).is_file());
    let audio_missing=job.project.audio.is_empty()||job.project.audio.iter().any(|p|!Path::new(p).is_file());
    if media_missing{
      let mut files=walkdir::WalkDir::new(&root).max_depth(2).into_iter().filter_map(Result::ok).map(|e|e.into_path()).filter(|p|p.is_file()&&is_image(p.to_string_lossy().as_ref())).collect::<Vec<_>>();
      files.sort_by_key(|p|p.file_name().map(|x|x.to_string_lossy().to_lowercase()).unwrap_or_default());
      if !files.is_empty(){job.project.media=files.into_iter().map(|p|p.to_string_lossy().into_owned()).collect();}
    }
    if audio_missing{
      let mut files=walkdir::WalkDir::new(&root).max_depth(2).into_iter().filter_map(Result::ok).map(|e|e.into_path()).filter(|p|p.is_file()&&is_audio(p)).collect::<Vec<_>>();
      files.sort_by_key(|p|p.file_name().map(|x|x.to_string_lossy().to_lowercase()).unwrap_or_default());
      if !files.is_empty(){job.project.audio=files.into_iter().map(|p|p.to_string_lossy().into_owned()).collect();}
    }
  }
  if job.ambient.as_ref().map(|p|!p.trim().is_empty()&&!Path::new(p).is_file()).unwrap_or(false){job.ambient=None;}
}
'''
if 'fn render_work_dir(' not in text:
    if helper_marker not in text:
        raise SystemExit('render stability: emit_timing marker not found')
    text = text.replace(helper_marker, helper_marker + helpers, 1)

# Mixed MP3/mono/stereo must be normalized before acrossfade.
text = text.replace('aresample=48000,asetpts=N/SR/TB', 'aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB')
text = text.replace('let cf=job.settings.crossfade_sec.clamp(0.0,10.0);let mut last=labels[0].clone();', 'let min_duration=durations.iter().copied().fold(f64::INFINITY,f64::min);let cf=job.settings.crossfade_sec.clamp(0.0,10.0).min((min_duration/3.0).max(0.05));let mut last=labels[0].clone();')

new_apply = r'''fn apply_effects_filter(mut graph:String,mut base:String,effects:&[EffectPreset],s:&RenderSettings,input_start:usize)->(String,String){
  for (n,e) in effects.iter().filter(|e|e.enabled&&!e.source.trim().is_empty()).enumerate(){
    let idx=input_start+n;let fx=format!("fx{n}");let next=format!("b{}",n+1);
    let target=((s.width as f64)*e.scale.clamp(0.05,1.5)).round().max(2.0) as u32;let target=if target%2==0{target}else{target+1};
    let scale=if e.fullscreen{format!("scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2:color=black@0",s.width,s.height,s.width,s.height)}else{format!("scale={}:-2:flags=lanczos",target)};
    let x=if e.fullscreen{"0".into()}else{format!("max(0,min(W-w,W*{}-w/2))",e.x.clamp(0.0,1.0))};
    let y=if e.fullscreen{"0".into()}else{format!("max(0,min(H-h,H*{}-h/2))",e.y.clamp(0.0,1.0))};
    if e.mode=="screen"||e.mode=="screen-cache"{
      let px=if e.fullscreen{"0".into()}else{format!("max(0,min(ow-iw,ow*{}-iw/2))",e.x.clamp(0.0,1.0))};
      let py=if e.fullscreen{"0".into()}else{format!("max(0,min(oh-ih,oh*{}-ih/2))",e.y.clamp(0.0,1.0))};
      graph.push_str(&format!(";[{idx}:v]fps={},format=rgba,{scale},pad={}:{}:'{px}':'{py}':color=black@0,setsar=1[{fx}];[{base}][{fx}]blend=all_mode=screen:all_opacity=1[{next}]",s.fps,s.width,s.height));
    }else{
      let prep=if e.mode=="prealpha"{format!("[{idx}:v]fps={},format=argb",s.fps)}else if e.mode=="luma"{format!("[{idx}:v]fps={},format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08",s.fps,e.luma_threshold,e.luma_tolerance)}else{format!("[{idx}:v]fps={},format=rgba,colorkey={}:{}:{}",s.fps,color_ffmpeg(&e.key_color),e.similarity.clamp(0.001,0.60),e.blend.clamp(0.001,0.35))};
      graph.push_str(&format!(";{prep},{scale}[{fx}];[{base}][{fx}]overlay=x='{x}':y='{y}':shortest=1:eof_action=repeat:format=auto[{next}]"));
    }
    base=next;
  }
  (graph,base)
}
'''
text, n = re.subn(r'fn apply_effects_filter\([\s\S]*?\n}\n\nasync fn prepare_overlays', new_apply + '\nasync fn prepare_overlays', text, count=1)
if n != 1:
    raise SystemExit('render stability: apply_effects_filter block not found')

new_prepare = r'''async fn prepare_overlays(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,encoder:&str,attempt:u32)->Result<(Vec<EffectPreset>,Vec<SubscribePreset>),String>{
  emit_progress(app,job,started,timer,26.0,"Проверяю кэш Effects и Subscribe",encoder,attempt,None);let mark=Instant::now();let mut fx=Vec::new();let mut subs=Vec::new();
  for e in &job.effects{
    if !e.enabled{continue}
    match cache::prepare(app,e,job.settings.fps).await{Ok(p)=>fx.push(p),Err(err)=>emit_warning(app,&job.project.id,&format!("Effect '{}' пропущен: {}",e.name,err))}
  }
  for s in &job.subscribes{
    if !s.effect.enabled{continue}
    match cache::prepare(app,&s.effect,job.settings.fps).await{Ok(effect)=>{let mut p=s.clone();p.effect=effect;subs.push(p)},Err(err)=>emit_warning(app,&job.project.id,&format!("Subscribe '{}' пропущен: {}",s.effect.name,err))}
  }
  emit_timing(app,&job.project.id,"effects-cache",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,31.0,"Кэш Effects и Subscribe готов",encoder,attempt,None);Ok((fx,subs))
}
'''
text, n = re.subn(r'async fn prepare_overlays\([\s\S]*?\n}\n\nfn active_effects_at', new_prepare + '\nfn active_effects_at', text, count=1)
if n != 1:
    raise SystemExit('render stability: prepare_overlays block not found')

# Prefix FFmpeg runtime errors with the exact stage.
text = text.replace('let (mut rx,child)=app.shell().sidecar("ffmpeg").map_err(|e|e.to_string())?.args(args).spawn().map_err(|e|e.to_string())?;', 'let (mut rx,child)=app.shell().sidecar("ffmpeg").map_err(|e|format!("{stage}: FFmpeg недоступен: {e}"))?.args(args).spawn().map_err(|e|format!("{stage}: не удалось запустить FFmpeg: {e}"))?;')
text = text.replace('Ok(None)=>return Err("FFmpeg закрыл канал без статуса завершения".into())', 'Ok(None)=>return Err(format!("{stage}: FFmpeg закрыл канал без статуса завершения"))')
text = text.replace('CommandEvent::Error(e)=>return Err(e),', 'CommandEvent::Error(e)=>return Err(format!("{stage}: {e}")),')
text = text.replace('if t.code.unwrap_or(1)!=0{return Err(if stderr_tail.trim().is_empty(){format!("FFmpeg завершился с кодом {:?}",t.code)}else{stderr_tail.lines().rev().take(12).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\\n")})}', 'if t.code.unwrap_or(1)!=0{return Err(if stderr_tail.trim().is_empty(){format!("{stage}: FFmpeg завершился с кодом {:?}",t.code)}else{format!("{stage}: {}",stderr_tail.lines().rev().take(12).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\\n"))})}')

new_render = r'''pub async fn render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<(),String>{
  let mut resolved_job=job.clone();refresh_project_paths(&mut resolved_job);let job=&resolved_job;
  for p in &job.project.media{if !Path::new(p).is_file(){return Err(format!("Не найден файл изображения/видео: {}",Path::new(p).file_name().and_then(|x|x.to_str()).unwrap_or(p)));}}
  for p in &job.project.audio{if !Path::new(p).is_file(){return Err(format!("Не найден аудиофайл: {}",Path::new(p).file_name().and_then(|x|x.to_str()).unwrap_or(p)));}}
  if job.project.media.is_empty(){return Err("В проекте нет изображения или видео".into())}
  if job.project.audio.is_empty(){return Err("В проекте нет музыки".into())}
  let started=chrono::Utc::now().timestamp_millis();let timer=Instant::now();let mut last_error=String::new();
  let requested_out_dir=PathBuf::from(&job.settings.output_dir);let out_dir=resolve_output_dir(app,&requested_out_dir)?;if out_dir!=requested_out_dir{emit_warning(app,&job.project.id,&format!("Выбранная папка недоступна. Результат будет сохранён в {}",out_dir.display()));}
  let out=unique_output(&out_dir,&job.project.name);
  for attempt in 1..=2{
    if cancel.load(Ordering::SeqCst){return Err(CANCELLED.into())}
    let _=std::fs::remove_file(&out);let encoder=if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};
    let pure_static=job.project.media.iter().all(|m|is_image(m))&&job.effects.iter().all(|e|!e.enabled)&&job.subscribes.iter().all(|e|!e.effect.enabled);
    let _=app.emit("engine-profile",json!({"id":job.project.id,"smartSize":pure_static,"targetVideoKbps":if pure_static{Some(static_video_kbps(&job.settings))}else{None::<u64>}}));
    emit_progress(app,job,started,&timer,1.0,"Анализ файлов",&encoder,attempt,None);let work=render_work_dir(app,&job.project.id,attempt)?;
    let result:Result<(Vec<f64>,f64),String>=async{
      emit_progress(app,job,started,&timer,4.0,"Проверяю самый быстрый движок",&encoder,attempt,None);
      let (source_master,master_duration)=build_source_master(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
      let (fx,subs)=prepare_overlays(app,job,started,&timer,&encoder,attempt).await?;
      let (cycle,durations,cycle_duration)=build_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
      let target=job.settings.duration_hours*3600.0;let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,&job.settings.duration_mode);
      let audio=build_long_audio(app,job,started,&timer,&work,&cycle,cycle_duration,final_duration,&encoder,attempt,&cancel).await?;
      let visual=assemble_visual(app,job,&source_master,master_duration,&fx,&subs,final_duration,&work,&encoder,attempt,&cancel,started,&timer).await?;
      let mux_mark=Instant::now();let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
      match visual{VisualSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),VisualSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}
      match audio{AudioSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}
      args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-movflags","+faststart","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
      run_ffmpeg(app,job,started,&timer,args,"Собираю итоговое видео",90.0,6.0,final_duration,&encoder,attempt,&cancel).await?;
      emit_timing(app,&job.project.id,"final-mux",mux_mark.elapsed().as_secs_f64());emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&encoder,attempt,None);verify_result(app,&out,final_duration,&job.settings).await?;
      let result_stem=out.file_stem().and_then(|x|x.to_str()).unwrap_or(&job.project.name);if let Err(err)=write_side_files(job,&out_dir,&durations,final_duration,result_stem){emit_warning(app,&job.project.id,&format!("Видео готово, но служебные файлы не записаны: {err}"));}
      Ok((durations,final_duration))
    }.await;
    match result{
      Ok((_durations,_fd))=>{let bytes=std::fs::metadata(&out).ok().map(|m|m.len());let bitrate=probe_video_bitrate(app,&out).await;let _=app.emit("render-done",Progress{id:job.project.id.clone(),status:"done".into(),progress:100.0,stage:"Готово".into(),started_at:Some(started),elapsed_sec:timer.elapsed().as_secs_f64(),eta_sec:Some(0.0),result_path:Some(out.to_string_lossy().into_owned()),result_bytes:bytes,actual_video_bitrate:bitrate,cpu_pct:None,ram_bytes:None,ram_total_bytes:None,ram_available_bytes:None,gpu_pct:None,encoder:Some(encoder),attempt:Some(attempt)});let _=std::fs::remove_dir_all(&work);return Ok(())},
      Err(e)=>{last_error=e;emit_warning(app,&job.project.id,&format!("Попытка {attempt} не прошла: {last_error}"));let _=std::fs::remove_dir_all(&work);let _=std::fs::remove_file(&out);if last_error==CANCELLED{return Err(last_error)}if attempt<2{emit_progress(app,job,started,&timer,2.0,"Hardware не прошёл — повторяю через software encoder",&encoder,attempt+1,None);}}
    }
  }
  Err(last_error)
}
'''
text, n = re.subn(r'pub async fn render_job\([\s\S]*$', new_render, text, count=1)
if n != 1:
    raise SystemExit('render stability: render_job block not found')

required = [
    'fn render_work_dir(',
    'fn refresh_project_paths(',
    'fn resolve_output_dir(',
    'software_encoder(&job.settings)',
    'Effect \'{}\' пропущен',
    'scale={}:-2:flags=lanczos',
    'aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo',
]
for marker in required:
    if marker not in text:
        raise SystemExit(f'render stability: missing marker {marker}')

p.write_text(text, encoding='utf-8')
print('ENDLUME alpha.8.25 render stability patch applied')
