from pathlib import Path

p = Path('src-tauri/src/render.rs')
s = p.read_text()

old = '''async fn prepare_overlays(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,encoder:&str,attempt:u32)->Result<(Vec<EffectPreset>,Vec<SubscribePreset>),String>{
  emit_progress(app,job,started,timer,26.0,"Проверяю кэш Effects и Subscribe",encoder,attempt,None);let mark=Instant::now();let mut fx=Vec::new();let mut subs=Vec::new();
  for e in &job.effects{fx.push(cache::prepare(app,e,job.settings.fps).await?)}
  for s in &job.subscribes{let mut p=s.clone();p.effect=cache::prepare(app,&s.effect,job.settings.fps).await?;subs.push(p)}
  emit_timing(app,&job.project.id,"effects-cache",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,31.0,"Кэш Effects и Subscribe готов",encoder,attempt,None);Ok((fx,subs))
}'''
new = '''async fn prepare_overlays(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,encoder:&str,attempt:u32)->Result<(Vec<EffectPreset>,Vec<SubscribePreset>),String>{
  emit_progress(app,job,started,timer,26.0,"Проверяю кэш Effects и Subscribe",encoder,attempt,None);let mark=Instant::now();let mut fx=Vec::new();let mut subs=Vec::new();
  for e in &job.effects{
    if !e.enabled||e.source.trim().is_empty(){continue}
    if !Path::new(&e.source).is_file(){let _=app.emit("overlay-warning",json!({"id":job.project.id,"kind":"effect","name":e.name,"reason":"source-missing"}));continue}
    match cache::prepare(app,e,job.settings.fps).await{Ok(v)=>fx.push(v),Err(err)=>{let _=app.emit("overlay-warning",json!({"id":job.project.id,"kind":"effect","name":e.name,"reason":err}));}}
  }
  for s in &job.subscribes{
    if !s.effect.enabled||s.effect.source.trim().is_empty(){continue}
    if !Path::new(&s.effect.source).is_file(){let _=app.emit("overlay-warning",json!({"id":job.project.id,"kind":"subscribe","name":s.effect.name,"reason":"source-missing"}));continue}
    let mut p=s.clone();match cache::prepare(app,&s.effect,job.settings.fps).await{Ok(v)=>{p.effect=v;subs.push(p)},Err(err)=>{let _=app.emit("overlay-warning",json!({"id":job.project.id,"kind":"subscribe","name":s.effect.name,"reason":err}));}}
  }
  emit_timing(app,&job.project.id,"effects-cache",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,31.0,"Кэш Effects и Subscribe готов",encoder,attempt,None);Ok((fx,subs))
}'''
if old in s:
    s = s.replace(old, new)
elif 'source-missing' not in s:
    raise SystemExit('prepare_overlays pattern not found')

old2 = '''let mut labels=Vec::new();let mut graph=String::new();for i in 0..job.project.audio.len(){if i>0{graph.push(';')}graph.push_str(&format!("[{i}:a]aresample=48000,asetpts=N/SR/TB[a{i}]"));labels.push(format!("a{i}"));}'''
new2 = '''let mut labels=Vec::new();let mut graph=String::new();for i in 0..job.project.audio.len(){if i>0{graph.push(';')}graph.push_str(&format!("[{i}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,aresample=48000,asetpts=N/SR/TB[a{i}]"));labels.push(format!("a{i}"));}'''
if old2 in s:
    s = s.replace(old2, new2)
elif 'aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo' not in s:
    raise SystemExit('audio normalization pattern not found')

# Repair stale scan paths after app update / moved project folder by rescanning the selected project directory.
marker = 'pub async fn render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<(),String>{\n'
if marker in s and 'fn refresh_project_paths(' not in s:
    helper = '''fn refresh_project_paths(job:&mut QueueJob)->Result<(),String>{
  const VIDEO_EXT:&[&str]=&["mp4","mov","m4v","mkv","webm","avi","wmv","flv","ts","mts","m2ts","mpg","mpeg","vob","3gp"];
  const AUDIO_EXT:&[&str]=&["mp3","wav","m4a","aac","flac","ogg","opus","aiff","aif","alac"];
  let dir=PathBuf::from(&job.project.path);if !dir.is_dir(){return Err(format!("Папка проекта не найдена: {}",job.project.path))}
  let stale=job.project.media.iter().chain(job.project.audio.iter()).any(|p|!Path::new(p).is_file());
  if !stale{return Ok(())}
  let mut media=Vec::<String>::new();let mut audio=Vec::<String>::new();
  for e in std::fs::read_dir(&dir).map_err(|e|format!("Не удалось перечитать папку проекта: {e}"))?.flatten(){
    let p=e.path();if !p.is_file(){continue}let ext=p.extension().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase();
    if IMAGE_EXT.contains(&ext.as_str())||VIDEO_EXT.contains(&ext.as_str()){media.push(p.to_string_lossy().into_owned())}else if AUDIO_EXT.contains(&ext.as_str()){audio.push(p.to_string_lossy().into_owned())}
  }
  media.sort();audio.sort();if media.is_empty(){return Err("После повторного сканирования не найдено изображение или видео".into())}if audio.is_empty(){return Err("После повторного сканирования не найдено ни одной песни".into())}
  job.project.media=media;job.project.audio=audio;Ok(())
}

'''
    s = s.replace(marker, helper + marker + '  let mut resolved_job=job.clone();refresh_project_paths(&mut resolved_job)?;let job=&resolved_job;\n', 1)
elif 'refresh_project_paths(&mut resolved_job)' not in s:
    raise SystemExit('render_job marker not found')

p.write_text(s)
print('ENDLUME render hotfix 8.17 applied')
