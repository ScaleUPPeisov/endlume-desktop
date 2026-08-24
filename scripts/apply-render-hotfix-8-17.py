from pathlib import Path

p = Path('src-tauri/src/render.rs')
s = p.read_text(encoding='utf-8')

# The production loop-fix script already owns overlay isolation and audio normalization.
# This hotfix adds one extra safety net: if persisted scan paths became stale after an
# app update / folder move, re-read the selected project directory before rendering.
marker = 'pub async fn render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<(),String>{\n'
if marker in s and 'fn refresh_project_paths(' not in s:
    helper = '''fn refresh_project_paths(job:&mut QueueJob)->Result<(),String>{
  const VIDEO_EXT:&[&str]=&["mp4","mov","m4v","mkv","webm","avi","wmv","flv","ts","mts","m2ts","mpg","mpeg","vob","3gp"];
  const AUDIO_EXT:&[&str]=&["mp3","wav","m4a","aac","flac","ogg","opus","aiff","aif","alac"];
  let dir=PathBuf::from(&job.project.path);
  if !dir.is_dir(){return Err(format!("Папка проекта не найдена: {}",job.project.path))}
  let stale=job.project.media.iter().chain(job.project.audio.iter()).any(|p|!Path::new(p).is_file());
  if !stale{return Ok(())}
  let mut media=Vec::<String>::new();let mut audio=Vec::<String>::new();
  for e in std::fs::read_dir(&dir).map_err(|e|format!("Не удалось перечитать папку проекта: {e}"))?.flatten(){
    let p=e.path();if !p.is_file(){continue}
    let ext=p.extension().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase();
    if IMAGE_EXT.contains(&ext.as_str())||VIDEO_EXT.contains(&ext.as_str()){media.push(p.to_string_lossy().into_owned())}
    else if AUDIO_EXT.contains(&ext.as_str()){audio.push(p.to_string_lossy().into_owned())}
  }
  media.sort();audio.sort();
  if media.is_empty(){return Err("После повторного сканирования не найдено изображение или видео".into())}
  if audio.is_empty(){return Err("После повторного сканирования не найдено ни одной песни".into())}
  job.project.media=media;job.project.audio=audio;Ok(())
}

'''
    s = s.replace(marker, helper + marker + '  let mut resolved_job=job.clone();refresh_project_paths(&mut resolved_job)?;let job=&resolved_job;\n', 1)
elif 'refresh_project_paths(&mut resolved_job)' not in s:
    raise SystemExit('render_job marker not found')

# Refuse to build unless the mandatory 8.17 protections from apply-render-loop-fix.py exist.
required = [
    'job.effects.iter().filter(|e|e.enabled)',
    'job.subscribes.iter().filter(|s|s.effect.enabled)',
    'aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo',
]
missing=[x for x in required if x not in s]
if missing:
    raise SystemExit('mandatory production render fixes missing: '+', '.join(missing))

p.write_text(s,encoding='utf-8')
print('ENDLUME render path-refresh hotfix applied')
