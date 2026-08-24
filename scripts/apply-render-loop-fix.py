from pathlib import Path

path = Path("src-tauri/src/render.rs")
text = path.read_text(encoding="utf-8")
changed = False

# 1) Crossfade video must use CFR + AVTB for FFmpeg xfade.
old_crossfade = '''      "crossfade"=>{let cf=s.crossfade_sec.min((d/3.0).max(0.15)).max(0.1);duration=d;args.extend(vec!["-i",media,"-i",media].into_iter().map(String::from));graph=format!("[0:v]trim=duration={d},setpts=PTS-STARTPTS[a];[1:v]trim=duration={d},setpts=PTS-STARTPTS[b];[a][b]xfade=transition=fade:duration={cf}:offset={},trim=start={cf}:duration={d},setpts=PTS-STARTPTS[x];{}[outv]",(d-cf).max(0.1),base_filter(s,"x"));},'''
new_crossfade = '''      "crossfade"=>{let cf=s.crossfade_sec.min((d/3.0).max(0.15)).max(0.1);duration=d;args.extend(vec!["-i",media,"-i",media].into_iter().map(String::from));graph=format!("[0:v]trim=duration={d},setpts=PTS-STARTPTS,fps={},settb=AVTB[a];[1:v]trim=duration={d},setpts=PTS-STARTPTS,fps={},settb=AVTB[b];[a][b]xfade=transition=fade:duration={cf}:offset={},trim=start={cf}:duration={d},setpts=PTS-STARTPTS[x];{}[outv]",s.fps,s.fps,(d-cf).max(0.1),base_filter(s,"x"));},'''
if old_crossfade in text:
    text = text.replace(old_crossfade, new_crossfade, 1)
    changed = True
elif new_crossfade not in text:
    raise SystemExit("Expected crossfade render source was not found; refusing to patch an unknown render pipeline")

# 2) Disabled or broken Effects/Subscribe MUST NOT break the base render.
# Missing sources and cache/chromakey preparation failures are isolated to that overlay.
old_overlays = '''  for e in &job.effects{fx.push(cache::prepare(app,e,job.settings.fps).await?)}
  for s in &job.subscribes{let mut p=s.clone();p.effect=cache::prepare(app,&s.effect,job.settings.fps).await?;subs.push(p)}'''
intermediate_overlays = '''  for e in job.effects.iter().filter(|e|e.enabled){
    if !Path::new(&e.source).is_file(){let _=app.emit("overlay-warning",json!({"id":job.project.id,"kind":"effect","name":e.name,"message":"Файл эффекта не найден — эффект пропущен"}));continue}
    fx.push(cache::prepare(app,e,job.settings.fps).await?)
  }
  for s in job.subscribes.iter().filter(|s|s.effect.enabled){
    if !Path::new(&s.effect.source).is_file(){let _=app.emit("overlay-warning",json!({"id":job.project.id,"kind":"subscribe","name":s.effect.name,"message":"Файл Subscribe не найден — кнопка пропущена"}));continue}
    let mut p=s.clone();p.effect=cache::prepare(app,&s.effect,job.settings.fps).await?;subs.push(p)
  }'''
new_overlays = '''  for e in job.effects.iter().filter(|e|e.enabled){
    if e.source.trim().is_empty(){continue}
    if !Path::new(&e.source).is_file(){let _=app.emit("overlay-warning",json!({"id":job.project.id,"kind":"effect","name":e.name,"message":"Файл эффекта не найден — эффект пропущен"}));continue}
    match cache::prepare(app,e,job.settings.fps).await{
      Ok(v)=>fx.push(v),
      Err(err)=>{let _=app.emit("overlay-warning",json!({"id":job.project.id,"kind":"effect","name":e.name,"message":format!("Эффект пропущен: {err}")}));}
    }
  }
  for s in job.subscribes.iter().filter(|s|s.effect.enabled){
    if s.effect.source.trim().is_empty(){continue}
    if !Path::new(&s.effect.source).is_file(){let _=app.emit("overlay-warning",json!({"id":job.project.id,"kind":"subscribe","name":s.effect.name,"message":"Файл Subscribe не найден — кнопка пропущена"}));continue}
    let mut p=s.clone();
    match cache::prepare(app,&s.effect,job.settings.fps).await{
      Ok(v)=>{p.effect=v;subs.push(p)},
      Err(err)=>{let _=app.emit("overlay-warning",json!({"id":job.project.id,"kind":"subscribe","name":s.effect.name,"message":format!("Subscribe пропущен: {err}")}));}
    }
  }'''
if old_overlays in text:
    text = text.replace(old_overlays, new_overlays, 1)
    changed = True
elif intermediate_overlays in text:
    text = text.replace(intermediate_overlays, new_overlays, 1)
    changed = True
elif new_overlays not in text:
    raise SystemExit("Expected overlay preparation source was not found")

# 3) Normalize arbitrary MP3/WAV inputs before acrossfade. Different source channel layouts/sample formats
# are common and must not make a normal project fail.
old_audio = '''let mut labels=Vec::new();let mut graph=String::new();for i in 0..job.project.audio.len(){if i>0{graph.push(';')}graph.push_str(&format!("[{i}:a]aresample=48000,asetpts=N/SR/TB[a{i}]"));labels.push(format!("a{i}"));}'''
new_audio = '''let mut labels=Vec::new();let mut graph=String::new();for i in 0..job.project.audio.len(){if i>0{graph.push(';')}graph.push_str(&format!("[{i}:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a{i}]"));labels.push(format!("a{i}"));}'''
if old_audio in text:
    text = text.replace(old_audio, new_audio, 1)
    changed = True
elif new_audio not in text:
    raise SystemExit("Expected audio normalization source was not found")

# Ambient also enters the same mix as normalized stereo.
old_ambient = '''graph.push_str(&format!(";[{ambient_index}:a]aresample=48000,volume=0.18[amb];[{music}][amb]amix=inputs=2:duration=first:weights='1 1':normalize=0,alimiter=limit=0.97[outa]"));'''
new_ambient = '''graph.push_str(&format!(";[{ambient_index}:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=0.18[amb];[{music}][amb]amix=inputs=2:duration=first:weights='1 1':normalize=0,alimiter=limit=0.97[outa]"));'''
if old_ambient in text:
    text = text.replace(old_ambient, new_ambient, 1)
    changed = True
elif new_ambient not in text:
    raise SystemExit("Expected ambient normalization source was not found")

if changed:
    path.write_text(text, encoding="utf-8")
    print("ENDLUME production render fixes applied")
else:
    print("ENDLUME production render fixes already applied")
