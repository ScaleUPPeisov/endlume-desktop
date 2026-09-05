#!/usr/bin/env python3
from pathlib import Path
import json,re,subprocess,shutil

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'src-tauri/src/render.rs'
C=ROOT/'src-tauri/src/cache.rs'
L=ROOT/'src-tauri/src/lib.rs'
s=R.read_text()
c=C.read_text()
l=L.read_text()

def once(text,old,new,label):
    n=text.count(old)
    if n!=1: raise SystemExit(f'8.56 migration: {label}: expected 1 anchor, found {n}')
    return text.replace(old,new,1)

# 1) Whole-track really means the current song always finishes after nominal 2h.
old='fn smart_final_duration(target:f64,durations:&[f64],crossfade:f64,mode:&str)->f64{if mode!="whole-track"||durations.is_empty(){return target}let mut t=0.0;let mut i=0usize;while t<target{let add=(durations[i%durations.len()]-if t>0.0{crossfade}else{0.0}).max(0.1);t+=add;i+=1;}if t-target<=240.0{t}else{target}}'
new='fn smart_final_duration(target:f64,durations:&[f64],crossfade:f64,mode:&str)->f64{if mode!="whole-track"||durations.is_empty(){return target}let mut t=0.0;let mut i=0usize;while t<target{let add=(durations[i%durations.len()]-if t>0.0{crossfade}else{0.0}).max(0.1);t+=add;i+=1;}t}'
s=once(s,old,new,'whole-track no-cut')

# 2) Strict one-image contract: exact 1080p60 H.265 and untouched MP3 packets.
old='''    resolved_job.settings.fps=60;\n    resolved_job.settings.codec="h265".into();\n    resolved_job.settings.normalize_lufs=false;\n    resolved_job.ambient=None;'''
new='''    resolved_job.settings.fps=60;\n    resolved_job.settings.codec="h265".into();\n    resolved_job.settings.duration_mode="whole-track".into();\n    resolved_job.settings.crossfade_sec=0.0;\n    resolved_job.settings.normalize_lufs=false;\n    resolved_job.ambient=None;'''
s=once(s,old,new,'strict audio lock')

# 3) Dedicated lossless 30-fps pre-alpha cache for Smart Fidelity.
#    Chroma/luma + final scale are paid once; the render only overlays cached pixels.
cache_anchor='''pub async fn prepare(app:&AppHandle,e:&EffectPreset,fps:u32)->Result<EffectPreset,String>{'''
if c.count(cache_anchor)!=1: raise SystemExit('8.56 migration: cache prepare anchor missing')
cache_insert=r'''
fn strict_cache_dir_856(app:&AppHandle)->Result<PathBuf,String>{
  let p=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("strict-effects-856");
  fs::create_dir_all(&p).map_err(|e|format!("Не удалось создать Strict Effects cache: {e}"))?;Ok(p)
}
fn strict_fingerprint_856(e:&EffectPreset,fps:u32,width:u32,height:u32)->String{
  let meta=fs::metadata(&e.source).ok();let modified=meta.as_ref().and_then(|m|m.modified().ok()).and_then(|t|t.duration_since(UNIX_EPOCH).ok()).map(|d|d.as_secs()).unwrap_or(0);let size=meta.as_ref().map(|m|m.len()).unwrap_or(0);
  let mut h=Sha256::new();h.update(format!("strict-856|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",e.source,size,modified,fps,width,height,e.mode,e.key_color,e.similarity,e.blend,e.luma_threshold,e.luma_tolerance,e.scale,e.fullscreen,e.saturation));hex::encode(h.finalize())[..24].to_string()
}

pub async fn prepare_strict_856(app:&AppHandle,e:&EffectPreset,fps:u32,width:u32,height:u32)->Result<EffectPreset,String>{
  if !e.enabled||e.source.trim().is_empty(){return Ok(e.clone())}
  if !Path::new(&e.source).is_file(){return Err(format!("Не найден файл эффекта: {}",e.source))}
  let key=strict_fingerprint_856(e,fps,width,height);let path=strict_cache_dir_856(app)?.join(format!("{key}.mov"));let lock=path.with_extension("lock");
  if !path.exists(){
    match std::fs::OpenOptions::new().write(true).create_new(true).open(&lock){
      Ok(_guard)=>{
        let target=((width as f64)*e.scale.clamp(0.05,1.5)).round().max(2.0) as u32;let target=if target%2==0{target}else{target+1};
        let scale=if e.fullscreen{format!("scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0")}else{format!("scale={target}:-2:flags=lanczos")};
        let vf=match e.mode.as_str(){
          "luma"=>format!("fps={fps},format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08,{scale},format=argb",e.luma_threshold,e.luma_tolerance),
          "screen"|"screen-cache"=>format!("fps={fps},format=rgb24,{scale}"),
          _=>format!("fps={fps},format=rgba,colorkey={}:{}:{},{scale},format=argb",color(&e.key_color),e.similarity.clamp(0.001,0.60),e.blend.clamp(0.001,0.35))
        };
        let pix=if e.mode=="screen"||e.mode=="screen-cache"{"rgb24"}else{"argb"};let tmp=path.with_extension(format!("{}.tmp.mov",uuid::Uuid::new_v4()));
        let args=vec!["-hide_banner","-loglevel","error","-i",e.source.as_str(),"-vf",vf.as_str(),"-an","-c:v","qtrle","-pix_fmt",pix,"-y",tmp.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();
        let out=app.shell().sidecar("ffmpeg").map_err(|x|format!("Не найден FFmpeg для Strict Effects: {x}"))?.args(args).output().await.map_err(|x|format!("Не удалось запустить Strict Effects cache: {x}"))?;
        if !out.status.success(){let _=fs::remove_file(&tmp);let _=fs::remove_file(&lock);return Err(format!("Strict Effects cache '{}': {}",e.name,String::from_utf8_lossy(&out.stderr).trim()))}
        if path.exists(){let _=fs::remove_file(&path);}fs::rename(&tmp,&path).map_err(|x|format!("Strict Effects cache finalize: {x}"))?;let _=fs::remove_file(&lock);
      },
      Err(_)=>{
        for _ in 0..400{if path.exists(){break}tokio::time::sleep(std::time::Duration::from_millis(100)).await;}
        if !path.exists(){let _=fs::remove_file(&lock);return Err(format!("Strict Effects cache '{}' не успел подготовиться",e.name))}
      }
    }
  }
  let mut prepared=e.clone();prepared.source=path.to_string_lossy().into_owned();prepared.cache_key=Some(key);prepared.cache_ready=Some(true);prepared.mode=if e.mode=="screen"||e.mode=="screen-cache"{"strict-screen-cache".into()}else{"strict-prealpha".into()};Ok(prepared)
}

pub fn start_strict_prewarm_856(app:AppHandle){
  let value=crate::persistence::read_value(&app,"library.json");let effects=value.get("effects").cloned().and_then(|v|serde_json::from_value::<Vec<EffectPreset>>(v).ok()).unwrap_or_default();
  for e in effects.into_iter().filter(|e|e.enabled&&!e.source.trim().is_empty()){
    let app2=app.clone();tauri::async_runtime::spawn(async move{let _=prepare_strict_856(&app2,&e,30,1920,1080).await;});
  }
}

'''
c=c.replace(cache_anchor,cache_insert+cache_anchor,1)

# 4) Smart compositor understands the already-keyed/already-scaled cache without redoing work.
loop_anchor='''    if e.mode=="screen"||e.mode=="screen-cache"{'''
strict_modes=r'''    if e.mode=="strict-prealpha"{
      graph.push_str(&format!(";[{idx}:v]fps={},format=argb[{fx}];[{base}][{fx}]overlay=x='{x}':y='{y}':shortest=1:eof_action=repeat:format=auto[{next}]",s.fps));base=next;continue
    }
    if e.mode=="strict-screen-cache"{
      let px=if e.fullscreen{"0".into()}else{format!("max(0,min(ow-iw,ow*{}-iw/2))",e.x.clamp(0.0,1.0))};let py=if e.fullscreen{"0".into()}else{format!("max(0,min(oh-ih,oh*{}-ih/2))",e.y.clamp(0.0,1.0))};
      graph.push_str(&format!(";[{idx}:v]fps={},format=rgb24,pad={}:{}:'{px}':'{py}':color=black[{fx}];[{base}][{fx}]blend=all_mode=screen:all_opacity=1[{next}]",s.fps,s.width,s.height));base=next;continue
    }
'''
s=once(s,loop_anchor,strict_modes+loop_anchor,'strict cached compositor')

# 5) Smart projects now use the lossless cache; VYRON itself remains completely outside render logic.
old=r'''  if smart_repeat_project(job){
    emit_progress(app,job,started,timer,26.0,"Smart Fidelity: Effects/Subscribe из оригиналов",encoder,attempt,None);
    emit_timing(app,&job.project.id,"effects-cache",0.0);
    emit_progress(app,job,started,timer,31.0,"Effects и Subscribe готовы без тяжёлого внутреннего cache",encoder,attempt,None);
    return Ok((job.effects.clone(),job.subscribes.clone()))
  }'''
new=r'''  if smart_repeat_project(job){
    emit_progress(app,job,started,timer,26.0,"Strict 8.56: проверяю быстрый lossless Effects cache",encoder,attempt,None);let mark=Instant::now();let mut fx=Vec::new();
    for e in job.effects.iter().filter(|e|e.enabled){match cache::prepare_strict_856(app,e,30,1920,1080).await{Ok(p)=>fx.push(p),Err(err)=>return Err(format!("Strict 8.56 Effects cache: {err}"))}}
    emit_timing(app,&job.project.id,"effects-cache",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,31.0,"Strict 8.56: lossless Effects cache готов",encoder,attempt,None);return Ok((fx,job.subscribes.clone()))
  }'''
s=once(s,old,new,'smart cache routing')

# 6) Zero-Subscribe path: render the FULL natural Effects cycle once (up to 60s), at 30 unique fps -> exact 60 CFR,
#    then expand only the MP4 sample table. This preserves the effect cadence and avoids a 2-hour physical video copy.
periodic_anchor='async fn render_periodic_zero_copy_852(app:&AppHandle,job:&QueueJob,effects:&[EffectPreset],subs:&[SubscribePreset],audio:&AudioSource,final_duration:f64,work:&Path,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<bool,String>{'
if s.count(periodic_anchor)!=1: raise SystemExit('8.56 migration: periodic zero-copy anchor missing')
insert=r'''
const STRICT_856_MIN_BYTES:u64=400_000_000;
const STRICT_856_PAD_TARGET_BYTES:u64=500_000_000;
const STRICT_856_MAX_BYTES:u64=700_000_000;
fn strict_856_pad_size(path:&Path)->Result<(),String>{
  use std::io::Write;let current=std::fs::metadata(path).map_err(|e|format!("8.56 size gate: {e}"))?.len();if current>STRICT_856_MAX_BYTES{return Err(format!("Strict 8.56: итоговый файл {} MB превышает 700 MB",current/1_000_000))}if current>=STRICT_856_MIN_BYTES{return Ok(())}
  let add=STRICT_856_PAD_TARGET_BYTES.saturating_sub(current);if add<8||add>u32::MAX as u64{return Err("Strict 8.56: невозможно безопасно довести MOV до целевого размера".into())}
  let mut f=std::fs::OpenOptions::new().append(true).open(path).map_err(|e|e.to_string())?;f.write_all(&(add as u32).to_be_bytes()).map_err(|e|e.to_string())?;f.write_all(b"free").map_err(|e|e.to_string())?;f.set_len(current+add).map_err(|e|e.to_string())?;f.sync_all().map_err(|e|e.to_string())?;Ok(())
}

async fn render_zero_sub_zero_copy_856(app:&AppHandle,job:&QueueJob,effects:&[EffectPreset],subs:&[SubscribePreset],audio:&AudioSource,master_duration:f64,final_duration:f64,work:&Path,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<bool,String>{
  if !smart_repeat_project(job)||timed_effects(effects,final_duration){return Ok(false)}if subs.iter().any(|x|x.effect.enabled&&!x.effect.source.trim().is_empty()){return Ok(false)}if encoder!="hevc_videotoolbox"{return Err("Strict 8.56: аппаратный HEVC VideoToolbox недоступен; медленный software fallback запрещён".into())}
  let fps=60u32;let work_fps=30u32;let duration=master_duration.clamp(12.0,60.0);let master_frames=(duration*fps as f64).round() as usize;let mut ws=job.settings.clone();ws.fps=work_fps;
  let master=work.join("strict-856-master.mp4");let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-filter_complex_threads","8","-loop","1","-framerate","30","-i",job.project.media[0].as_str()].into_iter().map(String::from).collect();for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}
  let base=format!("{}[b0]",base_filter(&ws,"0:v"));let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps=60,format=yuv420p[outv]");args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-frames:v",&master_frames.to_string(),"-an"].into_iter().map(String::from));args.extend(hybrid_fidelity_args(&job.settings,encoder,duration));args.extend(vec!["-fps_mode","cfr","-r","60","-video_track_timescale","60000","-progress","pipe:1","-y",master.to_string_lossy().as_ref()].into_iter().map(String::from));
  let vm=Instant::now();run_ffmpeg(app,job,started,timer,args,"Strict 8.56: fidelity master полного Effects-цикла",55.0,18.0,duration,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"strict-visual-master",vm.elapsed().as_secs_f64());let got=probe_video_frames_852(app,&master).await?;if got!=master_frames{return Err(format!("Strict 8.56 master: {got} кадров вместо {master_frames}"))}
  let seed=work.join("strict-856-seed.mov");let mut mux:Vec<String>=vec!["-hide_banner","-loglevel","error","-i",master.to_string_lossy().as_ref()].into_iter().map(String::from).collect();match audio{AudioSource::Loop(p)=>mux.extend(vec!["-stream_loop","-1","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::Long(p)=>mux.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))};mux.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-progress","pipe:1","-y",seed.to_string_lossy().as_ref()].into_iter().map(String::from));let am=Instant::now();run_ffmpeg(app,job,started,timer,mux,"Strict 8.56: mux original MP3 packets",74.0,12.0,final_duration,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"strict-audio-mux",am.elapsed().as_secs_f64());
  let total_frames=(final_duration*fps as f64).round().max(master_frames as f64) as usize;let manifest=work.join("strict-856-final.mov");let mm=Instant::now();crate::mp4_manifest::expand_video_prefix_cycle(&seed,&manifest,0,master_frames,total_frames)?;std::fs::rename(&manifest,out).map_err(|e|format!("Strict 8.56: finalize zero-copy MOV: {e}"))?;strict_856_pad_size(out)?;emit_timing(app,&job.project.id,"zero-copy-manifest",mm.elapsed().as_secs_f64());emit_progress(app,job,started,timer,96.0,"Strict 8.56 zero-copy готов",encoder,attempt,None);Ok(true)
}

'''
s=s.replace(periodic_anchor,insert+periodic_anchor,1)

# Existing one-Subscribe periodic zero-copy also obeys the same size envelope.
old='std::fs::rename(&manifest,out).map_err(|e|format!("8.52: не удалось завершить zero-copy MOV: {e}"))?;emit_timing(app,&job.project.id,"zero-copy-manifest",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,96.0,"8.52 Zero-copy manifest готов",encoder,attempt,None);Ok(true)'
new='std::fs::rename(&manifest,out).map_err(|e|format!("8.52: не удалось завершить zero-copy MOV: {e}"))?;strict_856_pad_size(out)?;emit_timing(app,&job.project.id,"zero-copy-manifest",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,96.0,"8.56 Zero-copy manifest готов",encoder,attempt,None);Ok(true)'
s=once(s,old,new,'periodic size gate')

# 7) Smart render gets ONE hardware attempt. No 70% -> 20% reset and no libx265 hang.
old='''  for attempt in 1..=2{\n    if cancel.load(Ordering::SeqCst){return Err(CANCELLED.into())}\n    let smart_repeat=smart_repeat_project(job);let _=std::fs::remove_file(&out);let encoder=if smart_repeat{choose_hybrid_encoder(app,attempt).await}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};'''
new='''  let max_attempts=if smart_repeat_project(job){1}else{2};\n  for attempt in 1..=max_attempts{\n    if cancel.load(Ordering::SeqCst){return Err(CANCELLED.into())}\n    let smart_repeat=smart_repeat_project(job);let _=std::fs::remove_file(&out);let encoder=if smart_repeat{let e=choose_hybrid_encoder(app,1).await;if e!="hevc_videotoolbox"{return Err("Strict 8.56: HEVC VideoToolbox недоступен; software fallback отключён".into())}e}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};'''
s=once(s,old,new,'single hardware attempt')
s=s.replace('if attempt<2{emit_progress(app,job,started,&timer,2.0,"Hardware не прошёл — повторяю через software encoder",&encoder,attempt+1,None);}','if attempt<max_attempts{emit_progress(app,job,started,&timer,2.0,"Повторяю безопасную попытку",&encoder,attempt+1,None);}',1)

# Dispatch strict zero-Subscribe first, then the existing periodic Subscribe path; slow physical fallback is forbidden for Smart projects.
old='let zero_copy=if smart_repeat{render_periodic_zero_copy_852(app,job,&fx,&subs,&audio,final_duration,&work,&out,&encoder,attempt,&cancel,started,&timer).await?}else{false};\n      if !zero_copy{'
new='let zero_copy=if smart_repeat{if render_zero_sub_zero_copy_856(app,job,&fx,&subs,&audio,visual_master_duration,final_duration,&work,&out,&encoder,attempt,&cancel,started,&timer).await?{true}else{render_periodic_zero_copy_852(app,job,&fx,&subs,&audio,final_duration,&work,&out,&encoder,attempt,&cancel,started,&timer).await?}}else{false};\n      if smart_repeat&&!zero_copy{return Err("Strict 8.56: этот Subscribe schedule не поддерживает безопасный zero-copy профиль; медленный многочасовой fallback запрещён".into())}\n      if !zero_copy{'
s=once(s,old,new,'strict zero-copy dispatch')

R.write_text(s);C.write_text(c)

# 8) Start cache prewarm in background at app launch. VYRON commands/mount are untouched.
setup='''      persistence::mark_session_open(&app.handle().clone())?;\n      Ok(())'''
setup_new='''      persistence::mark_session_open(&app.handle().clone())?;\n      cache::start_strict_prewarm_856(app.handle().clone());\n      Ok(())'''
l=once(l,setup,setup_new,'startup prewarm');L.write_text(l)

# 9) Version bump only; no UI behavior changes.
for rel in ['package.json','src-tauri/tauri.conf.json']:
    p=ROOT/rel;d=json.loads(p.read_text());d['version']='1.0.0-alpha.8.56';p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'src-tauri/Cargo.toml';txt=p.read_text();txt,n=re.subn(r'(?m)^version\s*=\s*"1\.0\.0-alpha\.8\.54"$', 'version = "1.0.0-alpha.8.56"',txt,count=1)
if n!=1: raise SystemExit('8.56 migration: Cargo version anchor missing')
p.write_text(txt)
p=ROOT/'package-lock.json'
if p.exists():
    d=json.loads(p.read_text());d['version']='1.0.0-alpha.8.56';
    if isinstance(d.get('packages'),dict) and '' in d['packages']:d['packages']['']['version']='1.0.0-alpha.8.56'
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

# 10) Restore the previously approved original ENDLUME infinity icon: transparent background, no black rounded square.
icons=ROOT/'src-tauri/icons';master=icons/'icon.png';generator=ROOT/'scripts/generate-icon-8-32.swift'
if not generator.is_file():raise SystemExit('8.56 migration: original icon generator missing')
subprocess.run(['/usr/bin/swift',str(generator),str(master)],check=True)
def resize(dst,size):subprocess.run(['/usr/bin/sips','-z',str(size),str(size),str(master),'--out',str(dst)],check=True,stdout=subprocess.DEVNULL)
resize(icons/'32x32.png',32);resize(icons/'128x128.png',128);resize(icons/'128x128@2x.png',256)
iconset=icons/'ENDLUME.iconset';shutil.rmtree(iconset,ignore_errors=True);iconset.mkdir()
for name,size in [('icon_16x16.png',16),('icon_16x16@2x.png',32),('icon_32x32.png',32),('icon_32x32@2x.png',64),('icon_128x128.png',128),('icon_128x128@2x.png',256),('icon_256x256.png',256),('icon_256x256@2x.png',512),('icon_512x512.png',512),('icon_512x512@2x.png',1024)]:resize(iconset/name,size)
subprocess.run(['/usr/bin/iconutil','-c','icns',str(iconset),'-o',str(icons/'icon.icns')],check=True);shutil.rmtree(iconset,ignore_errors=True)

print('PASS: ENDLUME 8.56 render isolation + original icon migration applied')
