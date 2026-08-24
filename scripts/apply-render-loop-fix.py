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

# 3) Normalize arbitrary MP3/WAV inputs before acrossfade.
old_audio = '''let mut labels=Vec::new();let mut graph=String::new();for i in 0..job.project.audio.len(){if i>0{graph.push(';')}graph.push_str(&format!("[{i}:a]aresample=48000,asetpts=N/SR/TB[a{i}]"));labels.push(format!("a{i}"));}'''
new_audio = '''let mut labels=Vec::new();let mut graph=String::new();for i in 0..job.project.audio.len(){if i>0{graph.push(';')}graph.push_str(&format!("[{i}:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a{i}]"));labels.push(format!("a{i}"));}'''
if old_audio in text:
    text = text.replace(old_audio, new_audio, 1)
    changed = True
elif new_audio not in text:
    raise SystemExit("Expected audio normalization source was not found")

old_ambient = '''graph.push_str(&format!(";[{ambient_index}:a]aresample=48000,volume=0.18[amb];[{music}][amb]amix=inputs=2:duration=first:weights='1 1':normalize=0,alimiter=limit=0.97[outa]"));'''
new_ambient = '''graph.push_str(&format!(";[{ambient_index}:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=0.18[amb];[{music}][amb]amix=inputs=2:duration=first:weights='1 1':normalize=0,alimiter=limit=0.97[outa]"));'''
if old_ambient in text:
    text = text.replace(old_ambient, new_ambient, 1)
    changed = True
elif new_ambient not in text:
    raise SystemExit("Expected ambient normalization source was not found")

# 4) Preview/render fidelity: RGB colorkey keeps visible pixel colours unchanged.
old_key='chromakey={}:{}:{}'
new_key='colorkey={}:{}:{}'
if old_key in text:
    text=text.replace(old_key,new_key)
    changed=True
elif new_key not in text:
    raise SystemExit("Expected chromakey/colorkey render filter was not found")

# 5) A second render attempt must NOT reuse the same failing hardware encoder.
old_encoder='let encoder=choose_encoder(app,&job.settings).await;'
new_encoder='let encoder=if attempt==1{choose_encoder(app,&job.settings).await}else if job.settings.codec.eq_ignore_ascii_case("h265"){"libx265".to_string()}else{"libx264".to_string()};'
if old_encoder in text:
    text=text.replace(old_encoder,new_encoder,1)
    changed=True
elif new_encoder not in text:
    raise SystemExit("Expected render encoder selection was not found")

# 6) Make FFmpeg failures identify the exact stage in logs/UI.
old_fail='''if t.code.unwrap_or(1)!=0{return Err(if stderr_tail.trim().is_empty(){format!("FFmpeg завершился с кодом {:?}",t.code)}else{stderr_tail.lines().rev().take(12).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\\n")})}'''
new_fail='''if t.code.unwrap_or(1)!=0{let detail=if stderr_tail.trim().is_empty(){format!("FFmpeg завершился с кодом {:?}",t.code)}else{stderr_tail.lines().rev().take(16).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\\n")};return Err(format!("Этап «{stage}» завершился ошибкой:\\n{detail}"))}'''
if old_fail in text:
    text=text.replace(old_fail,new_fail,1)
    changed=True
elif new_fail not in text:
    # Older formatting can differ; don't block build if stage context is already present.
    if 'Этап «{stage}» завершился ошибкой' not in text:
        print('warning: run_ffmpeg stage-context source pattern not found')

# 7) More tolerant final remux timestamps without re-encoding image or music.
old_mux='''"-c:v","copy","-c:a","copy","-progress","pipe:1","-y"'''
new_mux='''"-c:v","copy","-c:a","copy","-fflags","+genpts","-avoid_negative_ts","make_zero","-movflags","+faststart","-progress","pipe:1","-y"'''
if old_mux in text:
    text=text.replace(old_mux,new_mux,1)
    changed=True
elif new_mux not in text:
    raise SystemExit("Expected final stream-copy mux source was not found")

if changed:
    path.write_text(text, encoding="utf-8")
    print("ENDLUME production render fixes applied")
else:
    print("ENDLUME production render fixes already applied")
