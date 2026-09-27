from pathlib import Path
import re


def must(cond, msg):
    if not cond:
        raise SystemExit(f'8.33: {msg}')

# ---------------------------------------------------------------------------
# 1) External-drive safety: ignore macOS AppleDouble/resource-fork sidecars.
#    Files named ._cover.png start with AppleDouble magic 00 05 16 07 and were
#    exactly what FFmpeg reported as "Invalid PNG signature 0x516070020000".
# ---------------------------------------------------------------------------
p=Path('src-tauri/src/scan.rs'); s=p.read_text(encoding='utf-8')
if 'fn is_macos_sidecar(' not in s:
    marker='fn ext(p:&Path)->String{p.extension().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase()}\n'
    must(marker in s,'scan ext marker missing')
    s=s.replace(marker,marker+'fn is_macos_sidecar(p:&Path)->bool{let n=p.file_name().and_then(|x|x.to_str()).unwrap_or("");n==".DS_Store"||n.starts_with("._")||n.starts_with(".Spotlight-")||n.starts_with(".Trashes")}\n',1)
s=s.replace('if !p.is_file(){continue}let x=ext(&p);','if !p.is_file()||is_macos_sidecar(&p){continue}let x=ext(&p);')
must('is_macos_sidecar(&p)' in s,'scan sidecar filter not applied')
p.write_text(s,encoding='utf-8')

p=Path('src-tauri/src/live_preview.rs'); s=p.read_text(encoding='utf-8')
if 'fn is_macos_sidecar(' not in s:
    marker='fn ext(p:&Path)->String{p.extension().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase()}\n'
    must(marker in s,'live preview ext marker missing')
    s=s.replace(marker,marker+'fn is_macos_sidecar(p:&Path)->bool{let n=p.file_name().and_then(|x|x.to_str()).unwrap_or("");n==".DS_Store"||n.starts_with("._")||n.starts_with(".Spotlight-")||n.starts_with(".Trashes")}\n',1)
s=s.replace('.filter(|p|p.is_file()&&is_media(p)).collect::<Vec<_>>()','.filter(|p|p.is_file()&&!is_macos_sidecar(p)&&is_media(p)).collect::<Vec<_>>()')
old='let overlay=PathBuf::from(overlay_source);if !overlay.is_file(){return Err("Не найден файл Effects/Subscribe".into())}'
new='let overlay=PathBuf::from(overlay_source);if !overlay.is_file(){return Err("Не найден файл Effects/Subscribe".into())}if is_macos_sidecar(&overlay){return Err("Выбран служебный файл macOS (._*), а не настоящий Effects/Subscribe файл".into())}'
if old in s:s=s.replace(old,new,1)
must('!is_macos_sidecar(p)&&is_media(p)' in s,'live preview first_media sidecar filter missing')
p.write_text(s,encoding='utf-8')

# ---------------------------------------------------------------------------
# 2) Remove Noise 1 / Noise 2 completely. Old persisted JSON keys are harmless:
#    serde ignores unknown fields and the UI no longer exposes or renders them.
# ---------------------------------------------------------------------------
p=Path('src/types.ts'); s=p.read_text(encoding='utf-8')
s=s.replace('  noise1?: boolean;\n','').replace('  noise2?: boolean;\n','')
p.write_text(s,encoding='utf-8')

p=Path('src/store.ts'); s=p.read_text(encoding='utf-8')
s=s.replace(',noise1:false,noise2:false','')
p.write_text(s,encoding='utf-8')

p=Path('src-tauri/src/model.rs'); s=p.read_text(encoding='utf-8')
s=re.sub(r'\s*#\[serde\(default\)\]\s*pub noise1:bool,\s*#\[serde\(default\)\]\s*pub noise2:bool,','\n',s,count=1)
p.write_text(s,encoding='utf-8')

p=Path('src/pages/ProjectPage.tsx'); s=p.read_text(encoding='utf-8')
s=re.sub(r'\n\s*<section className="sectionBlock">\s*<div className="sectionTitle">ВСТРОЕННЫЕ ЭФФЕКТЫ</div>.*?</section>\s*\n','\n',s,count=1,flags=re.S)
p.write_text(s,encoding='utf-8')

# ---------------------------------------------------------------------------
# 3) Render path: keep all temporary heavy files on the selected output drive.
#    When output points to TOSHIBA SSD, source master, audio cache and visual
#    segments are created on that SSD instead of the nearly-full Mac system disk.
# ---------------------------------------------------------------------------
p=Path('src-tauri/src/render.rs'); r=p.read_text(encoding='utf-8')

# Remove the two built-in noise filters while keeping the rest of the 8.31 stack.
r=re.sub(
    r'fn base_filter\(s:&RenderSettings,label:&str\)->String\{.*?\n\}',
    'fn base_filter(s:&RenderSettings,label:&str)->String{format!("[{label}]scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,s.fps)}',
    r,count=1,flags=re.S)

if 'fn render_work_dir(' not in r:
    marker='fn fmt_ts(sec:f64)->String{'
    must(marker in r,'render work helper marker missing')
    helper='''fn render_work_dir(output:&Path,id:&str,attempt:u32)->Result<PathBuf,String>{
  let root=output.join(".ENDLUME-work");
  std::fs::create_dir_all(&root).map_err(|e|format!("Не удалось создать рабочую папку рендера на выбранном диске: {e}"))?;
  Ok(root.join(format!("{}-{}",safe_name(id),attempt)))
}

'''
    r=r.replace(marker,helper+marker,1)
r,n=re.subn(r'let work=std::env::temp_dir\(\)\.join\(format!\("endlume-\{\}-\{\}",job\.project\.id,attempt\)\);',
             'let work=render_work_dir(&out_dir,&job.project.id,attempt)?;',r,count=1)
must(n==1 or 'let work=render_work_dir(&out_dir,&job.project.id,attempt)?;' in r,'render workspace was not moved to output drive')

# Smart one-image projects use the ORIGINAL effect/subscribe files directly.
# This avoids giant qtrle lossless caches on the internal Mac disk and removes an
# unnecessary pre-encode generation before the short final master is built.
prepare_sig='async fn prepare_overlays(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,encoder:&str,attempt:u32)->Result<(Vec<EffectPreset>,Vec<SubscribePreset>),String>{\n'
if 'Smart Fidelity: Effects/Subscribe из оригиналов' not in r:
    must(prepare_sig in r,'prepare_overlays marker missing')
    direct='''  if smart_repeat_project(job){
    emit_progress(app,job,started,timer,26.0,"Smart Fidelity: Effects/Subscribe из оригиналов",encoder,attempt,None);
    emit_timing(app,&job.project.id,"effects-cache",0.0);
    emit_progress(app,job,started,timer,31.0,"Effects и Subscribe готовы без тяжёлого внутреннего cache",encoder,attempt,None);
    return Ok((job.effects.clone(),job.subscribes.clone()))
  }
'''
    r=r.replace(prepare_sig,prepare_sig+direct,1)

# ---------------------------------------------------------------------------
# 4) Fast Hybrid Fidelity. First attempt uses Apple VideoToolbox HEVC hardware;
#    software x265 CRF14 remains the automatic second-attempt fallback.
#    The target HEVC bitrate is chosen so a 2h result with original 320k MP3 is
#    roughly 0.8-1.0 GB for a mostly-static scene.
# ---------------------------------------------------------------------------
pat=r'fn hybrid_master_seconds\(_s:&RenderSettings\)->f64\{30\.0\}\n\nfn hybrid_fidelity_args\(s:&RenderSettings\)->Vec<String>\{.*?\n\}'
replacement=r'''fn hybrid_master_seconds(_s:&RenderSettings)->f64{8.0}

async fn hybrid_master_seconds_for_job(app:&AppHandle,job:&QueueJob)->f64{
  let mut d=hybrid_master_seconds(&job.settings);
  for e in job.effects.iter().filter(|e|e.enabled&&!e.source.trim().is_empty()){
    if let Ok(x)=probe_duration(app,&e.source).await{d=d.max(x.clamp(2.0,60.0));}
  }
  d.clamp(2.0,60.0)
}

fn hybrid_video_kbps(s:&RenderSettings)->u64{match s.width{0..=1920=>600,1921..=2560=>680,_=>760}}

fn hybrid_fidelity_args(s:&RenderSettings,encoder:&str,duration:f64)->Vec<String>{
  let g=(s.fps.max(1)*2).to_string();
  if encoder=="hevc_videotoolbox"{
    let avg=format!("{}k",hybrid_video_kbps(s));
    vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-b:v",&avg,"-maxrate","6M","-bufsize","16M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }else{
    let frames=(s.fps.max(1) as f64*duration.max(2.0)).round().max(1.0) as u32;
    let key=frames.to_string();let x265=format!("keyint={}:min-keyint={}:scenecut=0:open-gop=0",key,key);
    vec!["-c:v","libx265","-preset","ultrafast","-crf","14","-tune","ssim","-x265-params",&x265,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }
}

async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  let _=app;
  "libx265".into()
}'''
new_r,n=re.subn(pat,replacement,r,count=1,flags=re.S)
if n==1:r=new_r
else:
    must('fn hybrid_fidelity_args(s:&RenderSettings,encoder:&str,duration:f64)' in r,'hybrid encoder function replacement failed')

# Dynamic master length follows the continuous Effect loop instead of arbitrary 30 s.
old='if smart_repeat_project(job)&&job.project.media.len()==1&&is_image(&job.project.media[0]){emit_timing(app,&job.project.id,"master-loop",0.0);return Ok((PathBuf::from(&job.project.media[0]),hybrid_master_seconds(&job.settings)))}'
new='if smart_repeat_project(job)&&job.project.media.len()==1&&is_image(&job.project.media[0]){let d=hybrid_master_seconds_for_job(app,job).await;emit_timing(app,&job.project.id,"master-loop",0.0);return Ok((PathBuf::from(&job.project.media[0]),d))}'
if old in r:r=r.replace(old,new,1)
must('hybrid_master_seconds_for_job(app,job).await' in r,'dynamic Effect master length missing')

r=r.replace('if smart{args.extend(hybrid_fidelity_args(&job.settings));}','if smart{args.extend(hybrid_fidelity_args(&job.settings,encoder,master_duration));}')
r=r.replace('if smart_repeat_project(job){args.extend(hybrid_fidelity_args(&job.settings));}','if smart_repeat_project(job){args.extend(hybrid_fidelity_args(&job.settings,encoder,len));}')
must('hybrid_fidelity_args(&job.settings,encoder,master_duration)' in r,'fast master encoder call missing')
must('hybrid_fidelity_args(&job.settings,encoder,len)' in r,'fast subscribe encoder call missing')

r=r.replace('let encoder=if smart_repeat{"libx265".to_string()}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};',
            'let encoder=if smart_repeat{choose_hybrid_encoder(app,attempt).await}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};')
must('choose_hybrid_encoder(app,attempt).await' in r,'VideoToolbox selector missing')

# ---------------------------------------------------------------------------
# 5) Reuse identical Subscribe composites and avoid one whole extra 2h copy.
# ---------------------------------------------------------------------------
r=r.replace('enum VisualSource{Loop(PathBuf),Long(PathBuf)}','enum VisualSource{Loop(PathBuf),Long(PathBuf),Concat(PathBuf)}')

r=r.replace('let intervals=boundaries.windows(2).filter(|w|w[1]-w[0]>0.005).map(|w|(w[0],w[1])).collect::<Vec<_>>();let mut segments=Vec::new();',
            'let intervals=boundaries.windows(2).filter(|w|w[1]-w[0]>0.005).map(|w|(w[0],w[1])).collect::<Vec<_>>();let mut segments=Vec::new();let mut sub_cache:HashMap<String,PathBuf>=HashMap::new();')

old='if active_sub.is_empty(){copy_segment(app,job,&variant,vd,a,b-a,&seg,encoder,attempt,cancel,base,span,started,timer).await?;}else{render_sub_segment(app,job,&variant,vd,a,b-a,&active_sub,&seg,encoder,attempt,cancel,base,span,started,timer).await?;}segments.push(seg);'
new='''if active_sub.is_empty(){
      copy_segment(app,job,&variant,vd,a,b-a,&seg,encoder,attempt,cancel,base,span,started,timer).await?;segments.push(seg);
    }else{
      let phase=(a%vd.max(0.1)).max(0.0);let mut ids=active_sub.iter().map(|e|e.sub.effect.id.clone()).collect::<Vec<_>>();ids.sort();
      let ck=format!("{}|{:.3}|{:.3}|{}",k,phase,b-a,ids.join(","));
      if let Some(existing)=sub_cache.get(&ck){segments.push(existing.clone());}
      else{render_sub_segment(app,job,&variant,vd,a,b-a,&active_sub,&seg,encoder,attempt,cancel,base,span,started,timer).await?;sub_cache.insert(ck,seg.clone());segments.push(seg);}
    }'''
if old in r:r=r.replace(old,new,1)
must('let mut sub_cache:HashMap<String,PathBuf>' in r and 'sub_cache.insert(ck,seg.clone())' in r,'Subscribe composite reuse missing')

old='let long=work.join("video-long.mp4");let list=work.join("visual-concat.txt");let text=segments.iter().map(|p|format!("file \'{}\'",p.to_string_lossy().replace(\'\\\\\',"/"))).collect::<Vec<_>>().join("\\n");std::fs::write(&list,text).map_err(|e|e.to_string())?;let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-an","-c:v","copy","-progress","pipe:1","-y",long.to_string_lossy().as_ref()].into_iter().map(String::from).collect();run_ffmpeg(app,job,started,timer,args,"Склеиваю визуальную дорожку",86.0,4.0,final_duration,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());Ok(VisualSource::Long(long))'
if old in r:
    new='''let list=work.join("visual-concat.txt");let text=segments.iter().map(|p|format!("file '{}'",p.to_string_lossy().replace('\\\\',"/"))).collect::<Vec<_>>().join("\\n");std::fs::write(&list,text).map_err(|e|e.to_string())?;
  if smart_repeat_project(job){emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());return Ok(VisualSource::Concat(list))}
  let long=work.join("video-long.mp4");let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-an","-c:v","copy","-progress","pipe:1","-y",long.to_string_lossy().as_ref()].into_iter().map(String::from).collect();run_ffmpeg(app,job,started,timer,args,"Склеиваю визуальную дорожку",86.0,4.0,final_duration,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());Ok(VisualSource::Long(long))'''
    r=r.replace(old,new,1)
else:
    # Less brittle fallback: inject the smart return immediately after the concat list is written.
    needle='std::fs::write(&list,text).map_err(|e|e.to_string())?;let args=vec!["-hide_banner","-loglevel","error","-f","concat"'
    if needle in r:
        r=r.replace(needle,'std::fs::write(&list,text).map_err(|e|e.to_string())?;if smart_repeat_project(job){emit_timing(app,&job.project.id,"visual-plan",mark.elapsed().as_secs_f64());return Ok(VisualSource::Concat(list))}let args=vec!["-hide_banner","-loglevel","error","-f","concat"',1)
must('VisualSource::Concat(list)' in r,'smart visual concat shortcut missing')

old='match visual{VisualSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),VisualSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}'
new='match visual{VisualSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),VisualSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),VisualSource::Concat(p)=>args.extend(vec!["-f","concat","-safe","0","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}'
if old in r:r=r.replace(old,new,1)
must('VisualSource::Concat(p)=>args.extend' in r,'final mux concat input missing')

# Guard: requested feature removal must be complete in runtime code.
must('if s.noise1' not in r and 'if s.noise2' not in r,'Noise render code still present')

p.write_text(r,encoding='utf-8')

# Final cross-file guards.
for file_name in ['src/types.ts','src/store.ts','src-tauri/src/model.rs','src/pages/ProjectPage.tsx','src-tauri/src/render.rs']:
    body=Path(file_name).read_text(encoding='utf-8')
    must('Шум 1' not in body and 'Шум 2' not in body,'Noise UI text still present')

print('ENDLUME alpha.8.33 SSD/Fast Fidelity/AppleDouble/Noise removal patch applied')
