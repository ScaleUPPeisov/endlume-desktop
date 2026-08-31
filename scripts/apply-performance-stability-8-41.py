from pathlib import Path
import re


def must(cond, msg):
    if not cond:
        raise SystemExit(f'8.41: {msg}')

# ---------------------------------------------------------------------------
# 1/4/7/8 Render + audio: TRUE 60 FPS, real crossfade, continuous timestamps.
# IMPORTANT: do not touch the proven 8.36 500k video budget / short-master
# stream-copy architecture. That preserves the ~30s render and ~700-1000 MB size.
# ---------------------------------------------------------------------------
p=Path('src-tauri/src/render.rs')
r=p.read_text(encoding='utf-8')

# 8.36 intentionally forced 60 -> 30. Remove only that runtime clamp.
r=re.sub(
    r'\s*if resolved_job\.settings\.fps>30\{emit_warning\(app,&resolved_job\.project\.id,"Fidelity Lock:[^"]*"\);\}\n',
    '\n',r,count=1)
r=r.replace('resolved_job.settings.fps=resolved_job.settings.fps.min(30);','resolved_job.settings.fps=60;',1)
must('resolved_job.settings.fps=60;' in r,'Smart/Fidelity render is not forced to true 60 FPS')
must('resolved_job.settings.fps=resolved_job.settings.fps.min(30);' not in r,'old 30 FPS clamp survived')

# Strict Fidelity also disabled crossfade. Keep the size policy, but restore the
# user crossfade. Crossfade necessarily mixes samples, so the processed path uses
# the existing 320k high-quality AAC encoder rather than a low bitrate encode.
r=re.sub(
    r'\s*let processed_audio=resolved_job\.settings\.crossfade_sec>0\.01\|\|resolved_job\.settings\.normalize_lufs\|\|resolved_job\.ambient\.as_ref\(\)\.map\(\|x\|!x\.trim\(\)\.is_empty\(\)\)\.unwrap_or\(false\);\n\s*if processed_audio\{emit_warning\(app,&resolved_job\.project\.id,"Strict Fidelity:[^"]*"\);\}\n',
    '\n',r,count=1)
r=r.replace('    resolved_job.settings.crossfade_sec=0.0;\n','',1)
must('resolved_job.settings.crossfade_sec=0.0;' not in r,'Strict Fidelity still disables crossfade')

# Preserve the exact proven size budget. Never silently increase it in 8.41.
must('fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' in r,'8.36 500k size budget changed before 8.41')
must('"-maxrate","500k","-bufsize","4M"' in r,'8.36 x265 size/quality guard changed')
must('"-b:v","500k","-maxrate","4M","-bufsize","16M"' in r,'8.36 VideoToolbox size/quality guard changed')

# Replace the processed-audio helper structurally. This exact helper exists in
# the 8.38 baseline. The output is one 320k AAC cycle with normalized timestamps.
start=r.find('async fn build_lossless_processed_audio_cycle(')
end=r.find('\n\nasync fn build_source_master',start)
must(start>=0 and end>start,'processed audio helper missing')
new_audio=r'''async fn build_lossless_processed_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
  if job.project.audio.is_empty(){return Err("Нет песен".into())}
  let mut durations=Vec::new();
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
  for a in &job.project.audio{
    durations.push(probe_duration(app,a).await.unwrap_or(180.0).max(0.2));
    args.extend(vec!["-i",a.as_str()].into_iter().map(String::from));
  }
  let min_track=durations.iter().copied().fold(f64::INFINITY,f64::min);
  let cf=job.settings.crossfade_sec.clamp(0.0,10.0).min((min_track*0.40).max(0.0));
  let mut graph=String::new();
  for i in 0..job.project.audio.len(){
    if i>0{graph.push(';')}
    graph.push_str(&format!("[{i}:a]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a{i}]"));
  }
  let last=if job.project.audio.len()==1{"a0".to_string()}else if cf>0.01{
    let mut cur="a0".to_string();
    for i in 1..job.project.audio.len(){
      let out=format!("xf{i}");
      graph.push_str(&format!(";[{cur}][a{i}]acrossfade=d={cf}:c1=tri:c2=tri[{out}]"));
      cur=out;
    }
    cur
  }else{
    let inputs=(0..job.project.audio.len()).map(|i|format!("[a{i}]")).collect::<String>();
    graph.push_str(&format!(";{inputs}concat=n={}:v=0:a=1[joined]",job.project.audio.len()));
    "joined".to_string()
  };
  graph.push_str(&format!(";[{last}]aresample=48000:async=1:first_pts=0,alimiter=limit=0.98[outa]"));
  let cycle=work.join("audio-crossfade-gapless.m4a");
  let expected=(durations.iter().sum::<f64>()-cf*((durations.len().saturating_sub(1)) as f64)).max(0.2);
  let audio_encoder=choose_audio_encoder(app).await;
  args.extend(vec!["-filter_complex",&graph,"-map","[outa]"].into_iter().map(String::from));
  args.extend(audio_encoder_args(&audio_encoder));
  args.extend(vec!["-movflags","+faststart","-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"Кроссфейд между треками • HQ 320k",35.0,18.0,expected,encoder,attempt,cancel).await?;
  if !probe_audio_decodes(app,&cycle).await{return Err("Crossfade Audio: итоговая дорожка не декодируется".into())}
  let cycle_duration=probe_duration(app,cycle.to_string_lossy().as_ref()).await.unwrap_or(expected);
  Ok((cycle,durations,cycle_duration))
}

async fn materialize_continuous_audio(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,cycle:&Path,final_duration:f64,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<PathBuf,String>{
  let out=work.join("audio-continuous.m4a");
  let args=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-fflags","+genpts","-i",cycle.to_string_lossy().as_ref(),"-t",&final_duration.to_string(),"-map","0:a:0","-c:a","copy","-avoid_negative_ts","make_zero","-movflags","+faststart","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  run_ffmpeg(app,job,started,timer,args,"Фиксирую непрерывную аудиодорожку",53.0,4.0,final_duration,encoder,attempt,cancel).await?;
  if !probe_audio_decodes(app,&out).await{return Err("Crossfade Audio: непрерывная дорожка не декодируется".into())}
  Ok(out)
}'''
r=r[:start]+new_audio+r[end:]

# The processed smart-repeat branch must never loop the short M4A directly: that
# was the source of occasional ~1s discontinuities at loop boundaries.
anchor=r.find('build_lossless_processed_audio_cycle(app,job')
must(anchor>=0,'processed smart-audio branch missing')
loop_marker='(AudioSource::Loop(cycle),durations,final_duration)'
pos=r.find(loop_marker,anchor)
must(pos>=0,'processed audio loop marker missing')
replacement='let continuous=materialize_continuous_audio(app,job,started,&timer,&work,&cycle,final_duration,&encoder,attempt,&cancel).await?;\n          (AudioSource::Long(continuous),durations,final_duration)'
r=r[:pos]+replacement+r[pos+len(loop_marker):]
r=r.replace('"audioLossless":true','"audioLossless":false,"audioHighQuality320":true',1)
r=r.replace('Кроссфейд применён. После сведения музыка сохраняется в ALAC lossless — без повторного lossy-сжатия.','Кроссфейд применён. Переходы сведены в непрерывную HQ 320 кбит/с дорожку без пауз.',1)
must('audio-crossfade-gapless.m4a' in r and 'materialize_continuous_audio' in r,'gapless crossfade path missing')

# Final output must really advertise ~60fps, not merely have a UI setting of 60.
verify_start=r.find('async fn verify_result(')
verify_end=r.find('\n\npub async fn render_job',verify_start)
must(verify_start>=0 and verify_end>verify_start,'verify_result helper missing')
new_verify=r'''async fn verify_result(app:&AppHandle,out:&Path,expected:f64,s:&RenderSettings)->Result<(),String>{
  let d=probe_duration(app,out.to_string_lossy().as_ref()).await?;
  if (d-expected).abs()>4.0{return Err(format!("Финальный файл имеет неверную длительность: {:0.1} сек вместо {:0.1}",d,expected))}
  if !probe_has_audio(app,out).await{return Err("В финальном файле отсутствует аудиодорожка".into())}
  if !probe_audio_decodes(app,out).await{return Err("Аудиодорожка есть, но не воспроизводится/не декодируется".into())}
  let args=vec!["-v","error","-select_streams","v:0","-show_entries","stream=width,height,avg_frame_rate","-of","json",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  let (stdout,_)=output(app,"ffprobe",args).await?;
  let v:serde_json::Value=serde_json::from_slice(&stdout).map_err(|e|e.to_string())?;
  let stream=v.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()).ok_or("FFprobe не вернул видеопоток")?;
  let w=stream.get("width").and_then(|x|x.as_u64()).unwrap_or(0) as u32;
  let h=stream.get("height").and_then(|x|x.as_u64()).unwrap_or(0) as u32;
  if w!=s.width||h!=s.height{return Err(format!("Неверное разрешение результата: {}x{} вместо {}x{}",w,h,s.width,s.height))}
  let rate=stream.get("avg_frame_rate").and_then(|x|x.as_str()).unwrap_or("0/1");
  let mut it=rate.split('/');let n=it.next().and_then(|x|x.parse::<f64>().ok()).unwrap_or(0.0);let den=it.next().and_then(|x|x.parse::<f64>().ok()).unwrap_or(1.0).max(0.0001);let fps=n/den;
  if s.fps==60&&(fps<59.0||fps>61.0){return Err(format!("Финальный файл не 60 FPS: {:.3}",fps))}
  Ok(())
}'''
r=r[:verify_start]+new_verify+r[verify_end:]

# Preserve exact 1080p YouTube Fill and the proven size architecture.
must('force_original_aspect_ratio=increase' in r and 'crop={}:{}:(iw-ow)/2:(ih-oh)/2' in r,'8.38 16:9 Fill changed')
must('fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' in r,'500k video budget changed')
p.write_text(r,encoding='utf-8')

# ---------------------------------------------------------------------------
# 1/3/9 Effects: true-motion 60 FPS cache + despill.
# ---------------------------------------------------------------------------
p=Path('src-tauri/src/cache.rs');c=p.read_text(encoding='utf-8')
if 'fn despill_type(' not in c:
    marker='fn color(hex:&str)->String{format!("0x{}",hex.trim().trim_start_matches(\'#\').trim_start_matches("0x"))}\n'
    must(marker in c,'cache color helper missing')
    helper='''fn despill_type(hex:&str)->&'static str{\n  let raw=hex.trim().trim_start_matches('#');\n  if raw.len()==6{if let Ok(v)=u32::from_str_radix(raw,16){let g=(v>>8)&255;let b=v&255;if b>g{return "blue"}}}\n  "green"\n}\n'''
    c=c.replace(marker,marker+helper,1)

# Fingerprint includes despill and the new motion interpolation generation.
fp_pat=r'h\.update\(format!\("aspect-safe-v4\|\{\}\|\{\}\|\{\}\|\{\}\|\{\}\|\{\}\|\{\}\|\{\}\|\{\}\|\{\}\|\{\}",e\.source,size,modified,fps,e\.mode,e\.key_color,e\.similarity,e\.blend,e\.luma_threshold,e\.luma_tolerance,e\.saturation\)\);'
fp_new='h.update(format!("aspect-safe-v6-motion|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",e.source,size,modified,fps,e.mode,e.key_color,e.similarity,e.blend,e.luma_threshold,e.luma_tolerance,e.saturation,e.despill));'
c,n=re.subn(fp_pat,fp_new,c,count=1)
must(n==1 or 'aspect-safe-v6-motion' in c,'effect cache fingerprint migration failed')

old='''    let similarity=e.similarity.clamp(0.001,0.60);let blend=e.blend.clamp(0.001,0.35);
    let vf=match e.mode.as_str(){
      "luma"=>format!("fps={fps},format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08,format=argb",e.luma_threshold,e.luma_tolerance),
      "screen"=>format!("fps={fps},format=rgb24"),
      // RGB colorkey changes alpha only; kept pixels preserve original source RGB.
      _=>format!("fps={fps},format=rgba,colorkey={}:{}:{},format=argb",color(&e.key_color),similarity,blend)
    };'''
new='''    let similarity=e.similarity.clamp(0.001,0.60);let blend=e.blend.clamp(0.001,0.35);
    let motion=if fps>=50{format!("minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")}else{format!("fps={fps}")};
    let vf=match e.mode.as_str(){
      "luma"=>format!("{motion},format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08,format=argb",e.luma_threshold,e.luma_tolerance),
      "screen"=>format!("{motion},format=rgb24"),
      _=>format!("{motion},format=rgba,colorkey={}:{}:{},despill=type={}:mix={}:expand=0.20,format=argb",color(&e.key_color),similarity,blend,despill_type(&e.key_color),e.despill.clamp(0.0,1.0))
    };'''
if old in c:c=c.replace(old,new,1)
must('minterpolate=fps={fps}' in c,'true-motion effects interpolation missing')
must('despill=type={}:mix={}:expand=0.20' in c,'render cache despill missing')
p.write_text(c,encoding='utf-8')

# Live Preview proxy gets actual interpolated 60fps rather than duplicated frames.
p=Path('src-tauri/src/live_preview.rs');lp=p.read_text(encoding='utf-8')
lp=lp.replace('scale=640:-2:flags=fast_bilinear,fps=60','scale=640:-2:flags=fast_bilinear,minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1',1)
must('minterpolate=fps=60:mi_mode=mci' in lp,'60fps Live Preview interpolation missing')
p.write_text(lp,encoding='utf-8')

# Persistence must not zero-out despill after every save/load.
p=Path('src-tauri/src/persistence.rs');pr=p.read_text(encoding='utf-8')
old='if obj.get("despill").and_then(Value::as_f64).unwrap_or(0.0)!=0.0{obj.insert("despill".into(),json!(0.0));changed=true;}'
new='let despill=obj.get("despill").and_then(Value::as_f64).unwrap_or(0.0);if despill<=0.0{obj.insert("despill".into(),json!(0.35));changed=true;}'
if old in pr:pr=pr.replace(old,new,1)
must('json!(0.35)' in pr and 'despill<=0.0' in pr,'persistence despill migration missing')
p.write_text(pr,encoding='utf-8')

# Editor exposes despill and new presets default to 0.35.
p=Path('src/pages/Editors.tsx');ed=p.read_text(encoding='utf-8')
ed=ed.replace('  despill: 0,','  despill: 0.35,',1)
ed=ed.replace("similarity: 0.10, blend: 0.06, saturation: 1, despill: 0 }","similarity: 0.10, blend: 0.06, saturation: 1, despill: 0.35 }")
blend='<SmallRange label="Blend / мягкость края" value={current.blend} min={0.001} max={0.35} step={0.001} onChange={(value) => patch({ blend: value })} />'
slider='<SmallRange label="Despill / убрать зелёный ореол" value={current.despill} min={0} max={1} step={0.01} onChange={(value) => patch({ despill: value })} />'
if 'Despill / убрать зелёный ореол' not in ed:
    ed=ed.replace(blend,blend+'\n            '+slider)
must(ed.count('Despill / убрать зелёный ореол')>=2,'despill controls missing in Effects/Subscribe')
p.write_text(ed,encoding='utf-8')

# WebGL preview uses the same visual despill concept.
p=Path('src/components/LiveCompositePreview.tsx');lv=p.read_text(encoding='utf-8')
shader_start=lv.find('    gl.shaderSource(fs,`')
shader_end=lv.find('`);\n    gl.compileShader',shader_start)
must(shader_start>=0 and shader_end>shader_start,'WebGL shader marker missing')
shader_end+=3
new_shader='''    gl.shaderSource(fs,`precision mediump float;varying vec2 v;uniform sampler2D tex;uniform vec3 key;uniform float sim;uniform float blend;uniform float dsp;uniform float mode;uniform float lthr;uniform float ltol;void main(){vec4 px=texture2D(tex,v);vec3 c=px.rgb;float a=px.a;if(mode<.5){float d=distance(c,key)/1.7320508;float lo=max(0.,sim);float hi=min(1.,lo+max(.001,blend));a*=smoothstep(lo,hi,d);if(key.g>=key.b){float sp=max(0.,c.g-max(c.r,c.b));c.g=max(0.,c.g-sp*dsp);}else{float sp=max(0.,c.b-max(c.r,c.g));c.b=max(0.,c.b-sp*dsp);}}else if(mode<1.5){float l=dot(c,vec3(.2126,.7152,.0722));float lo=max(0.,lthr-ltol);float hi=min(1.,lthr+ltol);a*=smoothstep(lo,hi,l);}gl_FragColor=vec4(c,a);}`);'''
lv=lv[:shader_start]+new_shader+lv[shader_end:]
lv=lv.replace("uBlend=gl.getUniformLocation(program,'blend'),uMode=","uBlend=gl.getUniformLocation(program,'blend'),uDsp=gl.getUniformLocation(program,'dsp'),uMode=",1)
lv=lv.replace("gl.uniform1f(uBlend,Math.max(.001,Math.min(.35,e.blend)));gl.uniform1f(uMode","gl.uniform1f(uBlend,Math.max(.001,Math.min(.35,e.blend)));gl.uniform1f(uDsp,Math.max(0,Math.min(1,e.despill||0)));gl.uniform1f(uMode",1)
must('uniform float dsp' in lv and 'gl.uniform1f(uDsp' in lv,'WebGL despill wiring missing')
p.write_text(lv,encoding='utf-8')

# ---------------------------------------------------------------------------
# 2/6 UI stability: stop serializing 100+ finished projects and batch progress
# once per animation frame. No design/layout changes.
# ---------------------------------------------------------------------------
p=Path('src/store.ts');s=p.read_text(encoding='utf-8')
s=s.replace("width:1920,height:1080,fps:30,codec:'h265'","width:1920,height:1080,fps:60,codec:'h265'",1)
s=s.replace("durationMode:'whole-track',loopMode:'image',crossfadeSec:0,normalizeLufs:false,","durationMode:'whole-track',loopMode:'image',crossfadeSec:3,normalizeLufs:false,",1)
old_lib='setLibrary:(v)=>set({effects:v.effects||[],subscribes:v.subscribes||[],ambient:v.ambient,libraryLoaded:true}),' 
if old_lib in s:
    s=s.replace(old_lib,'setLibrary:(v)=>set({effects:(v.effects||[]).map(e=>({...e,despill:e.despill>0?e.despill:0.35})),subscribes:(v.subscribes||[]).map(e=>({...e,despill:e.despill>0?e.despill:0.35})),ambient:v.ambient,libraryLoaded:true}),',1)
pat=r"\}\),\{name:'endlume-1-ui',version:4,migrate:\(persisted:any\)=>\{.*?\},partialize:\(s\)=>\(\{settings:s\.settings,lastRoot:s\.lastRoot,projects:s\.projects\}\)\}\)\);"
repl="}),{name:'endlume-1-ui',version:6,migrate:(persisted:any)=>{const p:any=persisted||{};if(p.settings){p.settings={...p.settings,width:1920,height:1080,fps:60,crossfadeSec:3,normalizeLufs:false,codec:'h265'};}p.projects=[];return p;},partialize:(s)=>({settings:s.settings,lastRoot:s.lastRoot})}));"
s,n=re.subn(pat,repl,s,count=1,flags=re.S)
must(n==1 or 'version:6,migrate:' in s,'Zustand v6 migration failed')
must('projects:s.projects' not in s[s.rfind("name:'endlume-1-ui'"):],'render history is still persisted')
must('p.projects=[]' in s and 'fps:60' in s and 'crossfadeSec:3' in s,'startup cleanup/defaults missing')
p.write_text(s,encoding='utf-8')

p=Path('src/pages/App.tsx');a=p.read_text(encoding='utf-8')
marker='    const off:Promise<()=>void>[]=[];\n'
if 'progressPending=new Map<string,any>()' not in a:
    must(marker in a,'App listener marker missing')
    batching='''    const progressPending=new Map<string,any>();let progressRaf:number|undefined;
    const flushRenderProgress=()=>{progressRaf=undefined;if(progressPending.size===0)return;const batch=new Map(progressPending);progressPending.clear();useApp.setState(state=>({projects:state.projects.map(p=>{const next=batch.get(p.id);return next?{...p,...compactPayload(next)}:p})}));};
'''
    a=a.replace(marker,batching+marker,1)
a=a.replace("    off.push(listen<any>('render-progress',e=>patchProject(e.payload.id,compactPayload(e.payload))));","    off.push(listen<any>('render-progress',e=>{const p=e.payload;if(!p?.id)return;progressPending.set(p.id,p);if(progressRaf===undefined)progressRaf=requestAnimationFrame(flushRenderProgress)}));",1)
a=a.replace('disposed=true;if(updateTimer)window.clearTimeout(updateTimer);if(updateInterval)window.clearInterval(updateInterval);','disposed=true;if(updateTimer)window.clearTimeout(updateTimer);if(updateInterval)window.clearInterval(updateInterval);if(progressRaf!==undefined)cancelAnimationFrame(progressRaf);progressPending.clear();',1)
must('requestAnimationFrame(flushRenderProgress)' in a,'60fps render-progress batching missing')
p.write_text(a,encoding='utf-8')

# Lightweight compositing only for the live effect surfaces; do NOT transform
# .pageScene/.content because ProjectPage contains a fixed footer.
p=Path('src/motion-polish.css');css=p.read_text(encoding='utf-8')
perf='''\n/* ENDLUME 8.41: WKWebView 60fps compositing hints; no layout/design changes. */\n.liveGpuOverlay,.liveOverlayCanvas{will-change:transform;transform:translateZ(0);backface-visibility:hidden;}\n.queueCard{content-visibility:auto!important;contain:layout paint style!important;contain-intrinsic-size:90px!important;}\n'''
if 'ENDLUME 8.41: WKWebView 60fps compositing hints' not in css:css+=perf
p.write_text(css,encoding='utf-8')

# ---------------------------------------------------------------------------
# 10 About creator (idempotent; 8.40 already has it on the bootstrap path).
# ---------------------------------------------------------------------------
p=Path('src/pages/SettingsPage.tsx');st=p.read_text(encoding='utf-8')
if 'Kirill Peisov' not in st:
    marker='<span>UI <b>Tauri 2</b></span>'
    must(marker in st,'About marker missing')
    st=st.replace(marker,marker+'<span>Создатель <b>Kirill Peisov</b></span><span>Email <b>peisov.business@gmail.com</b></span>',1)
must('Kirill Peisov' in st and 'peisov.business@gmail.com' in st,'About creator data missing')
p.write_text(st,encoding='utf-8')

print('ENDLUME alpha.8.41 targeted 1-10 patch applied; unrelated features untouched')
