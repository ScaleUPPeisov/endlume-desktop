from pathlib import Path
import re

VERSION='1.0.0-alpha.8.31'

# ---------- TypeScript settings ----------
types=Path('src/types.ts')
t=types.read_text(encoding='utf-8')
if '  noise1?: boolean;\n' not in t:
    marker='  encoderPreference: EncoderPreference;\n'
    if marker not in t: raise SystemExit('8.31: RenderSettings TS marker missing')
    t=t.replace(marker,marker+'  noise1?: boolean;\n  noise2?: boolean;\n',1)
types.write_text(t,encoding='utf-8')

store=Path('src/store.ts')
s=store.read_text(encoding='utf-8')
old="  outputDir:'',preset:'fast',encoderPreference:'auto'\n"
new="  outputDir:'',preset:'fast',encoderPreference:'auto',noise1:false,noise2:false\n"
if old in s:s=s.replace(old,new,1)
elif 'noise1:false,noise2:false' not in s:raise SystemExit('8.31: initialSettings marker missing')
store.write_text(s,encoding='utf-8')

# ---------- Rust settings + render ----------
model=Path('src-tauri/src/model.rs')
m=model.read_text(encoding='utf-8')
old='  pub encoder_preference:String,\n}'
new='  pub encoder_preference:String,\n  #[serde(default)] pub noise1:bool,\n  #[serde(default)] pub noise2:bool,\n}'
if old in m:m=m.replace(old,new,1)
elif 'pub noise1:bool' not in m:raise SystemExit('8.31: Rust RenderSettings marker missing')
model.write_text(m,encoding='utf-8')

render=Path('src-tauri/src/render.rs')
r=render.read_text(encoding='utf-8')
old_base='fn base_filter(s:&RenderSettings,label:&str)->String{format!("[{label}]scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,s.fps)}'
new_base='''fn base_filter(s:&RenderSettings,label:&str)->String{
  let mut f=format!("[{label}]scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,s.fps);
  // Built-in CapCut-style grain alternatives. Static-uniform grain is intentional:
  // it stays visually stable and compresses efficiently inside the short master.
  if s.noise1{f.push_str(",noise=alls=4:allf=u");}
  if s.noise2{f.push_str(",noise=alls=7:allf=u");}
  f
}'''
if old_base in r:r=r.replace(old_base,new_base,1)
elif 'if s.noise1' not in r:raise SystemExit('8.31: base_filter marker missing')

# Lossless processed-audio helper. Crossfade necessarily changes samples, but ALAC
# stores the resulting signal losslessly: no second AAC/MP3 generation loss.
helper_marker='async fn build_source_master(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,f64),String>{\n'
helper=r'''async fn build_lossless_processed_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
  if job.project.audio.is_empty(){return Err("Нет песен".into())}
  let mut durations=Vec::new();
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
  for a in &job.project.audio{
    durations.push(probe_duration(app,a).await.unwrap_or(180.0).max(0.2));
    args.extend(vec!["-i",a.as_str()].into_iter().map(String::from));
  }
  let ambient_index=job.project.audio.len();
  if let Some(a)=job.ambient.as_ref().filter(|p|!p.trim().is_empty()){
    args.extend(vec!["-stream_loop","-1","-i",a.as_str()].into_iter().map(String::from));
  }
  let mut graph=String::new();
  for i in 0..job.project.audio.len(){
    if i>0{graph.push(';')}
    graph.push_str(&format!("[{i}:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a{i}]"));
  }
  let cf=job.settings.crossfade_sec.clamp(0.0,10.0);
  let last=if job.project.audio.len()==1{"a0".to_string()}else if cf>0.01{
    let mut cur="a0".to_string();
    for i in 1..job.project.audio.len(){let out=format!("xf{i}");graph.push_str(&format!(";[{cur}][a{i}]acrossfade=d={cf}:c1=tri:c2=tri[{out}]"));cur=out;}
    cur
  }else{
    let inputs=(0..job.project.audio.len()).map(|i|format!("[a{i}]")).collect::<String>();
    graph.push_str(&format!(";{inputs}concat=n={}:v=0:a=1[joined]",job.project.audio.len()));
    "joined".to_string()
  };
  if job.settings.normalize_lufs{graph.push_str(&format!(";[{last}]loudnorm=I=-14:TP=-1.5:LRA=11[music]"));}else{graph.push_str(&format!(";[{last}]anull[music]"));}
  if job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false){
    graph.push_str(&format!(";[{ambient_index}:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,volume=0.18[amb];[music][amb]amix=inputs=2:duration=first:weights='1 1':normalize=0[outa]"));
  }else{graph.push_str(";[music]anull[outa]");}
  let cycle=work.join("audio-processed-lossless.m4a");
  let expected=(durations.iter().sum::<f64>()-cf*((durations.len().saturating_sub(1)) as f64)).max(0.2);
  args.extend(vec!["-filter_complex",&graph,"-map","[outa]","-c:a","alac","-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from));
  let stage=if cf>0.01{"Кроссфейд между треками: lossless ALAC"}else if job.settings.normalize_lufs{"Нормализация музыки: lossless ALAC"}else{"Обрабатываю музыку: lossless ALAC"};
  run_ffmpeg(app,job,started,timer,args,stage,35.0,18.0,expected,encoder,attempt,cancel).await?;
  if !probe_audio_decodes(app,&cycle).await{return Err("Lossless Audio: итоговый ALAC не декодируется".into())}
  let cycle_duration=probe_duration(app,cycle.to_string_lossy().as_ref()).await.unwrap_or(expected);
  Ok((cycle,durations,cycle_duration))
}

'''
if 'async fn build_lossless_processed_audio_cycle(' not in r:
    if helper_marker not in r:raise SystemExit('8.31: build_source_master marker missing')
    r=r.replace(helper_marker,helper+helper_marker,1)

old_audio='''      let target=job.settings.duration_hours*3600.0;
      let (audio,durations,final_duration)=if smart_repeat{
        if job.settings.crossfade_sec>0.01||job.settings.normalize_lufs||job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false){
          emit_warning(app,&job.project.id,"Original Fidelity: чтобы не портить музыку, кроссфейд, LUFS-нормализация и ambient для этого рендера не применяются.");
        }
        match build_original_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await{
          Ok((cycle,durations,_cycle_duration))=>{
            let final_duration=smart_final_duration(target,&durations,0.0,&job.settings.duration_mode);
            let _=app.emit("engine-profile",json!({"id":job.project.id,"audioOriginal":true,"audioLossless":false}));
            (AudioSource::Loop(cycle),durations,final_duration)
          },
          Err(reason)=>{
            emit_warning(app,&job.project.id,&format!("Точный MP3 stream-copy невозможен ({reason}). Перехожу на ALAC: без повторного lossy-сжатия, но файл может быть больше 1 ГБ."));
            let (cycle,durations,_cycle_duration)=build_lossless_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
            let final_duration=smart_final_duration(target,&durations,0.0,&job.settings.duration_mode);
            let _=app.emit("engine-profile",json!({"id":job.project.id,"audioOriginal":false,"audioLossless":true}));
            (AudioSource::Loop(cycle),durations,final_duration)
          }
        }
      }else{
        let (cycle,durations,cycle_duration)=build_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
        let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,&job.settings.duration_mode);
        let audio=build_long_audio(app,job,started,&timer,&work,&cycle,cycle_duration,final_duration,&encoder,attempt,&cancel).await?;
        (audio,durations,final_duration)
      };'''
new_audio='''      let target=job.settings.duration_hours*3600.0;
      let (audio,durations,final_duration)=if smart_repeat{
        let processed=job.settings.crossfade_sec>0.01||job.settings.normalize_lufs||job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false);
        if processed{
          let (cycle,durations,_cycle_duration)=build_lossless_processed_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
          let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,&job.settings.duration_mode);
          let _=app.emit("engine-profile",json!({"id":job.project.id,"audioOriginal":false,"audioLossless":true,"crossfadeApplied":job.settings.crossfade_sec>0.01}));
          if job.settings.crossfade_sec>0.01{emit_warning(app,&job.project.id,"Кроссфейд применён. После сведения музыка сохраняется в ALAC lossless — без повторного lossy-сжатия.");}
          (AudioSource::Loop(cycle),durations,final_duration)
        }else{
          match build_original_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await{
            Ok((cycle,durations,_cycle_duration))=>{
              let final_duration=smart_final_duration(target,&durations,0.0,&job.settings.duration_mode);
              let _=app.emit("engine-profile",json!({"id":job.project.id,"audioOriginal":true,"audioLossless":false,"crossfadeApplied":false}));
              (AudioSource::Loop(cycle),durations,final_duration)
            },
            Err(reason)=>{
              emit_warning(app,&job.project.id,&format!("Точный MP3 stream-copy невозможен ({reason}). Перехожу на ALAC lossless."));
              let (cycle,durations,_cycle_duration)=build_lossless_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
              let final_duration=smart_final_duration(target,&durations,0.0,&job.settings.duration_mode);
              let _=app.emit("engine-profile",json!({"id":job.project.id,"audioOriginal":false,"audioLossless":true,"crossfadeApplied":false}));
              (AudioSource::Loop(cycle),durations,final_duration)
            }
          }
        }
      }else{
        let (cycle,durations,cycle_duration)=build_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
        let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,&job.settings.duration_mode);
        let audio=build_long_audio(app,job,started,&timer,&work,&cycle,cycle_duration,final_duration,&encoder,attempt,&cancel).await?;
        (audio,durations,final_duration)
      };'''
if old_audio in r:r=r.replace(old_audio,new_audio,1)
elif '"crossfadeApplied":job.settings.crossfade_sec>0.01' not in r:raise SystemExit('8.31: Original Fidelity audio branch marker missing')

# Timecodes must reflect the crossfade that is now really rendered.
r=r.replace('let cf=if smart_repeat_project(job){0.0}else{job.settings.crossfade_sec.max(0.0)};','let cf=job.settings.crossfade_sec.max(0.0);')
render.write_text(r,encoding='utf-8')

# ---------- Project UI ----------
project=Path('src/pages/ProjectPage.tsx')
x=project.read_text(encoding='utf-8')
# Remove the large Original/Hybrid Fidelity explainer card.
x,n=re.subn(r'<div style=\{\{margin:"4px 0 18px".*?</small></div>(?=<div className="bigControl"><div><b>Битрейт</b>)','',x,count=1,flags=re.S)
x=x.replace('Для обычных видео-проектов. В Original Fidelity этот лимит не используется для принудительного ухудшения картинки или Effects.','Для обычных видео-проектов. Для статичного проекта ENDLUME автоматически выбирает компактный режим без жёсткого ухудшения качества.')
old_cross='<div className="bigControl compactControl"><div><b>Кроссфейд между треками</b><small>В Original Fidelity автоматически отключается: иначе исходные MP3 пришлось бы декодировать и заново сжимать. Для обычных видео можно использовать значение ниже.</small></div><div className="bigValue small">{settings.crossfadeSec} сек</div><Range value={settings.crossfadeSec} min={0} max={10} onChange={v=>patchSettings({crossfadeSec:v})} minLabel="0 сек" maxLabel="10 сек"/></div>'
new_cross='''<div className="bigControl compactControl"><div><b>Кроссфейд между треками</b><small>{settings.crossfadeSec>0?'Включён. Переход реально сводится между песнями и сохраняется в ALAC lossless без повторного lossy-сжатия.':'Выключен. Совместимые MP3 можно сохранить bitstream-copy без повторного кодирования.'}</small></div><div className="bigValue small">{settings.crossfadeSec>0?`${settings.crossfadeSec} сек`:'Выкл'}</div><Range value={settings.crossfadeSec} min={0} max={10} step={0.5} onChange={v=>patchSettings({crossfadeSec:v})} minLabel="Выкл" maxLabel="10 сек"/></div><div className="durationPresets"><button className={settings.crossfadeSec===0?'selected':''} onClick={()=>patchSettings({crossfadeSec:0})}>ВЫКЛ</button>{[1,2,3,5,7,10].map(v=><button className={settings.crossfadeSec===v?'selected':''} key={`cf-${v}`} onClick={()=>patchSettings({crossfadeSec:v})}>{v}с</button>)}</div>'''
if old_cross in x:x=x.replace(old_cross,new_cross,1)
elif 'Переход реально сводится между песнями' not in x:raise SystemExit('8.31: crossfade UI marker missing')

noise_section='''
    <section className="sectionBlock">
      <div className="sectionTitle">ВСТРОЕННЫЕ ЭФФЕКТЫ</div>
      <div className="featureRow"><span className="featureIcon blue"><Icon name="effects"/></span><div><b>Шум 1</b><small>Мелкое плёночное зерно. Встроено в ENDLUME, внешний файл не нужен.</small></div><div className="rowButtons"><button className={settings.noise1?'selected':''} onClick={()=>patchSettings({noise1:!settings.noise1})}>{settings.noise1?'ВЫКЛЮЧИТЬ':'ВКЛЮЧИТЬ'}</button></div></div>
      <div className="featureRow" style={{marginTop:10}}><span className="featureIcon blue"><Icon name="effects"/></span><div><b>Шум 2</b><small>Более заметное ретро-зерно. Можно включать отдельно или вместе с «Шум 1».</small></div><div className="rowButtons"><button className={settings.noise2?'selected':''} onClick={()=>patchSettings({noise2:!settings.noise2})}>{settings.noise2?'ВЫКЛЮЧИТЬ':'ВКЛЮЧИТЬ'}</button></div></div>
    </section>
'''
ambient_marker='    <section className="sectionBlock">\n      <div className="sectionTitle">ФОНОВЫЙ ЗВУК</div>'
if 'ВСТРОЕННЫЕ ЭФФЕКТЫ' not in x:
    if ambient_marker not in x:raise SystemExit('8.31: ambient section marker missing')
    x=x.replace(ambient_marker,noise_section+'\n'+ambient_marker,1)
project.write_text(x,encoding='utf-8')

# ---------- Render Center: always show what is actually happening ----------
render_page=Path('src/pages/RenderPage.tsx')
u=render_page.read_text(encoding='utf-8')
old_calc="const lower=active.stage.toLowerCase();const currentIndex=stageNames.findIndex(s=>lower.includes(s.toLowerCase()));return stageNames.map((s,i)=>{"
new_calc="const lower=(active.stage||'').toLowerCase();const exact=stageNames.findIndex(s=>lower.includes(s.toLowerCase()));const fallback=Math.max(0,Math.min(stageNames.length-1,Math.floor((active.progress/100)*(stageNames.length-1))));const currentIndex=active.status==='done'?stageNames.length-1:(exact>=0?exact:fallback);return stageNames.map((s,i)=>{"
if old_calc in u:u=u.replace(old_calc,new_calc,1)
elif 'const fallback=Math.max(0,Math.min(stageNames.length-1' not in u:raise SystemExit('8.31: RenderPage stage calc marker missing')
old_card='<div className="stageCard"><div className="stageCardTitle">ПРОЦЕСС</div>{(()=>{'
new_card='''<div className="stageCard"><div className="stageCardTitle">ПРОЦЕСС</div><div style={{margin:"0 0 12px",padding:"12px 14px",border:"1px solid #344064",borderRadius:10,background:"rgba(83,94,255,.07)",display:"grid",gridTemplateColumns:"1fr auto",gap:"4px 12px"}}><small style={{gridColumn:"1 / -1",color:"#7f8aa8"}}>СЕЙЧАС ВЫПОЛНЯЕТСЯ</small><b style={{color:"#eef2ff",fontSize:13}}>{active.stage||'Подготовка'}</b><strong style={{color:"#8d7cff"}}>{active.progress.toFixed(2)}%</strong></div>{(()=>{'''
if old_card in u:u=u.replace(old_card,new_card,1)
elif 'СЕЙЧАС ВЫПОЛНЯЕТСЯ' not in u:raise SystemExit('8.31: live stage card marker missing')
# Remove verbose fidelity status from finished card; technical details stay out of the main UI.
verbose='{active.originalFidelity?<span className="smartSizeLine">Hybrid Fidelity: short-master x265 CRF14 + stream-copy • аудио {active.audioOriginal?"MP3 bitstream-copy + исправленные таймстампы":active.audioLossless?"ALAC lossless fallback":"проверяется"} • QuickTime MOV • цель ≈ 0.7–1.0 ГБ при статичной сцене</span>:active.smartSize&&<span className="smartSizeLine">Smart Size: статичное изображение</span>}'
u=u.replace(verbose,'')
render_page.write_text(u,encoding='utf-8')

# Remove verbose Settings copy too.
settings=Path('src/pages/SettingsPage.tsx')
ss=settings.read_text(encoding='utf-8')
ss=ss.replace('Hybrid Fidelity 8.28: короткий x265 master повторяется через stream-copy, совместимые MP3 сохраняются без аудиоперекодирования и упаковываются в QuickTime MOV для корректного звука на Mac.','Качество и формат результата ENDLUME выбирает автоматически под проект.')
settings.write_text(ss,encoding='utf-8')

print('ENDLUME alpha.8.31 runtime UX/crossfade/noise patch applied')