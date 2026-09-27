from pathlib import Path
import re


def must(cond, msg):
    if not cond:
        raise SystemExit(f'8.39: {msg}')

# ---------------------------------------------------------------------------
# Render: true 60 FPS for the one-image workflow, while preserving the short
# master + stream-copy architecture, exact 1920x1080 YouTube Fill and size cap.
# ---------------------------------------------------------------------------
p = Path('src-tauri/src/render.rs')
r = p.read_text(encoding='utf-8')

# 8.35/8.36 deliberately clamped smart-repeat to 30 FPS. Remove only that cap.
r = re.sub(
    r'\s*if resolved_job\.settings\.fps>30\{emit_warning\(app,&resolved_job\.project\.id,"(?:Strict|Fidelity)[^"]*"\);\}\n',
    '\n', r, count=1)
r = r.replace('resolved_job.settings.fps=resolved_job.settings.fps.min(30);', 'resolved_job.settings.fps=60;', 1)
must('resolved_job.settings.fps=60;' in r, 'smart-repeat is not forced to true 60 FPS')

# Crossfade was forcibly disabled by Strict Fidelity. Keep LUFS/ambient policy as
# before, but respect the user crossfade value again.
r = re.sub(
    r'\s*let processed_audio=resolved_job\.settings\.crossfade_sec>0\.01\|\|resolved_job\.settings\.normalize_lufs\|\|resolved_job\.ambient\.as_ref\(\)\.map\(\|x\|!x\.trim\(\)\.is_empty\(\)\)\.unwrap_or\(false\);\n\s*if processed_audio\{emit_warning\(app,&resolved_job\.project\.id,"Strict Fidelity:[^"]*"\);\}\n',
    '\n', r, count=1)
r = r.replace('    resolved_job.settings.crossfade_sec=0.0;\n', '', 1)
must('resolved_job.settings.crossfade_sec=0.0;' not in r, 'Strict Fidelity still disables crossfade')

# 60 FPS animated overlays need more instantaneous headroom, but the two-hour
# payload still stays below 1 GB with 320k audio: 700k video + 320k audio.
r = r.replace('fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}', 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{700}', 1)
r = r.replace('"-maxrate","500k","-bufsize","4M"', '"-maxrate","700k","-bufsize","8M"', 1)
r = r.replace('"-b:v","500k","-maxrate","4M","-bufsize","16M"', '"-b:v","700k","-maxrate","8M","-bufsize","24M"', 1)
must('"-maxrate","700k"' in r, '60 FPS Hybrid Fidelity bitrate headroom missing')

# ---------------------------------------------------------------------------
# Audio: real crossfade + timestamp normalization. With crossfade enabled the
# samples necessarily change, so encode one compact 320k AAC cycle, then make a
# continuous long stream with packet copy. With crossfade off, the existing
# exact MP3 bitstream-copy path remains untouched.
# ---------------------------------------------------------------------------
start = r.find('async fn build_lossless_processed_audio_cycle(')
end = r.find('\n\nasync fn build_source_master', start)
must(start >= 0 and end > start, 'processed audio helper missing')
new_audio = r'''async fn build_lossless_processed_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
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
  args.extend(vec!["-filter_complex",&graph,"-map","[outa]","-c:a","aac","-b:a","320k","-ar","48000","-ac","2","-movflags","+faststart","-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"Кроссфейд между треками • HQ 320k",35.0,18.0,expected,encoder,attempt,cancel).await?;
  if !probe_audio_decodes(app,&cycle).await{return Err("Crossfade Audio: итоговый AAC не декодируется".into())}
  let cycle_duration=probe_duration(app,cycle.to_string_lossy().as_ref()).await.unwrap_or(expected);
  Ok((cycle,durations,cycle_duration))
}

async fn materialize_continuous_audio(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,cycle:&Path,final_duration:f64,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<PathBuf,String>{
  let out=work.join("audio-continuous.m4a");
  let args=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-i",cycle.to_string_lossy().as_ref(),"-t",&final_duration.to_string(),"-map","0:a:0","-c:a","copy","-fflags","+genpts","-avoid_negative_ts","make_zero","-movflags","+faststart","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  run_ffmpeg(app,job,started,timer,args,"Фиксирую непрерывную аудиодорожку",53.0,4.0,final_duration,encoder,attempt,cancel).await?;
  if !probe_audio_decodes(app,&out).await{return Err("Crossfade Audio: непрерывная дорожка не декодируется".into())}
  Ok(out)
}'''
r = r[:start] + new_audio + r[end:]

# In the smart processed-audio branch, materialize one continuous timeline so
# the final mux cannot introduce a one-second gap when looping the cycle.
anchor = r.find('build_lossless_processed_audio_cycle(app,job')
must(anchor >= 0, 'smart processed-audio branch missing')
loop_marker = '(AudioSource::Loop(cycle),durations,final_duration)'
pos = r.find(loop_marker, anchor)
must(pos >= 0, 'processed audio still-loop marker missing')
replacement = 'let continuous=materialize_continuous_audio(app,job,started,&timer,&work,&cycle,final_duration,&encoder,attempt,&cancel).await?;\n          (AudioSource::Long(continuous),durations,final_duration)'
r = r[:pos] + replacement + r[pos+len(loop_marker):]
# Correct profile/warning wording for the compact HQ crossfade branch.
tail_start = anchor
r = r[:tail_start] + r[tail_start:].replace('"audioLossless":true', '"audioLossless":false,"audioHighQuality320":true', 1)
r = r.replace('Кроссфейд применён. После сведения музыка сохраняется в ALAC lossless — без повторного lossy-сжатия.', 'Кроссфейд применён. Переходы сведены в непрерывную AAC 320 кбит/с дорожку без пауз.', 1)
must('audio-crossfade-gapless.m4a' in r and 'materialize_continuous_audio' in r, 'gapless crossfade audio path missing')

# ---------------------------------------------------------------------------
# Chroma key: the model already contains despill, but render never used it.
# Apply the same green/blue spill suppression to direct Smart-Fidelity overlays.
# ---------------------------------------------------------------------------
color_marker='fn color_ffmpeg(hex:&str)->String{format!("0x{}",hex.trim().trim_start_matches(\'#\').trim_start_matches("0x"))}\n'
if 'fn chroma_despill_type(' not in r:
    must(color_marker in r, 'color helper marker missing')
    helper=r'''fn chroma_despill_type(hex:&str)->&'static str{
  let raw=hex.trim().trim_start_matches('#');
  if raw.len()==6{if let Ok(v)=u32::from_str_radix(raw,16){let g=(v>>8)&255;let b=v&255;if b>g{return "blue"}}}
  "green"
}
'''
    r=r.replace(color_marker,color_marker+helper,1)
old='format!("[{idx}:v]fps={},format=rgba,chromakey={}:{}:{}",s.fps,color_ffmpeg(&e.key_color),e.similarity.max(0.00001),e.blend)'
new='format!("[{idx}:v]fps={},format=rgba,chromakey={}:{}:{},despill=type={}:mix={}:expand=0.20",s.fps,color_ffmpeg(&e.key_color),e.similarity.max(0.00001),e.blend,chroma_despill_type(&e.key_color),e.despill.clamp(0.0,1.0))'
if old in r:
    r=r.replace(old,new,1)
must('despill=type={}:mix={}:expand=0.20' in r, 'render chroma despill missing')
p.write_text(r,encoding='utf-8')

# ---------------------------------------------------------------------------
# Effects cache: key by despill and apply it before qtrle alpha cache.
# ---------------------------------------------------------------------------
p=Path('src-tauri/src/cache.rs'); c=p.read_text(encoding='utf-8')
if 'fn despill_type(' not in c:
    marker='fn color(hex:&str)->String{format!("0x{}",hex.trim().trim_start_matches(\'#\').trim_start_matches("0x"))}\n'
    must(marker in c,'cache color helper marker missing')
    c=c.replace(marker,marker+r'''fn despill_type(hex:&str)->&'static str{
  let raw=hex.trim().trim_start_matches('#');
  if raw.len()==6{if let Ok(v)=u32::from_str_radix(raw,16){let g=(v>>8)&255;let b=v&255;if b>g{return "blue"}}}
  "green"
}
''',1)
old_fp='h.update(format!("aspect-safe-v4|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",e.source,size,modified,fps,e.mode,e.key_color,e.similarity,e.blend,e.luma_threshold,e.luma_tolerance,e.saturation));'
new_fp='h.update(format!("aspect-safe-v5|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",e.source,size,modified,fps,e.mode,e.key_color,e.similarity,e.blend,e.luma_threshold,e.luma_tolerance,e.saturation,e.despill));'
if old_fp in c:c=c.replace(old_fp,new_fp,1)
old_vf='_=>format!("fps={fps},format=rgba,colorkey={}:{}:{},format=argb",color(&e.key_color),similarity,blend)'
new_vf='_=>format!("fps={fps},format=rgba,colorkey={}:{}:{},despill=type={}:mix={}:expand=0.20,format=argb",color(&e.key_color),similarity,blend,despill_type(&e.key_color),e.despill.clamp(0.0,1.0))'
if old_vf in c:c=c.replace(old_vf,new_vf,1)
must('aspect-safe-v5' in c and 'despill=type={}:mix={}:expand=0.20' in c,'cache chroma despill missing')
p.write_text(c,encoding='utf-8')

# ---------------------------------------------------------------------------
# Store: 60 FPS/crossfade defaults, discard the old 100-job persisted history,
# keep active queue recovery in Rust, and normalize old chroma presets.
# ---------------------------------------------------------------------------
p=Path('src/store.ts'); s=p.read_text(encoding='utf-8')
s=s.replace("width:1920,height:1080,fps:30,codec:'h265'", "width:1920,height:1080,fps:60,codec:'h265'",1)
s=s.replace("durationMode:'whole-track',loopMode:'image',crossfadeSec:0,normalizeLufs:false,", "durationMode:'whole-track',loopMode:'image',crossfadeSec:3,normalizeLufs:false,",1)
# Normalize already-saved effects with despill=0 without changing presets otherwise.
old_lib='setLibrary:(v)=>set({effects:v.effects||[],subscribes:v.subscribes||[],ambient:v.ambient,libraryLoaded:true}),' 
new_lib='setLibrary:(v)=>set({effects:(v.effects||[]).map(e=>({...e,despill:e.despill>0?e.despill:0.35})),subscribes:(v.subscribes||[]).map(e=>({...e,despill:e.despill>0?e.despill:0.35})),ambient:v.ambient,libraryLoaded:true}),' 
if old_lib in s:s=s.replace(old_lib,new_lib,1)
# Replace the v4 persisted-settings tail as one unit. Projects are intentionally
# dropped from localStorage; backend queueSnapshot/recovery remains authoritative.
pat=r"\}\),\{name:'endlume-1-ui',version:4,migrate:\(persisted:any\)=>\{.*?\},partialize:\(s\)=>\(\{settings:s\.settings,lastRoot:s\.lastRoot,projects:s\.projects\}\)\}\)\);"
repl="}),{name:'endlume-1-ui',version:5,migrate:(persisted:any)=>{const p:any=persisted||{};if(p.settings){p.settings={...p.settings,width:1920,height:1080,fps:60,crossfadeSec:3,normalizeLufs:false,codec:'h265'};}p.projects=[];return p;},partialize:(s)=>({settings:s.settings,lastRoot:s.lastRoot})}));"
s2,n=re.subn(pat,repl,s,count=1,flags=re.S)
if n==1:s=s2
must("fps:60,codec:'h265'" in s and 'crossfadeSec:3' in s,'60 FPS/crossfade defaults missing')
must("version:5,migrate:" in s and 'p.projects=[]' in s,'large persisted queue migration missing')
must('projects:s.projects' not in s[s.rfind("name:'endlume-1-ui'"):], 'projects are still persisted')
p.write_text(s,encoding='utf-8')

# ---------------------------------------------------------------------------
# Frontend main-thread load: batch render-progress events instead of mutating the
# entire React/Zustand project list for every FFmpeg progress packet.
# ---------------------------------------------------------------------------
p=Path('src/pages/App.tsx'); a=p.read_text(encoding='utf-8')
if 'progressPending=new Map<string,any>()' not in a:
    marker='    const off:Promise<()=>void>[]=[];\n'
    must(marker in a,'App event-listener marker missing')
    batching='''    const progressPending=new Map<string,any>();let progressTimer:number|undefined;
    const flushRenderProgress=()=>{progressTimer=undefined;if(progressPending.size===0)return;const batch=new Map(progressPending);progressPending.clear();useApp.setState(state=>({projects:state.projects.map(p=>{const next=batch.get(p.id);return next?{...p,...compactPayload(next)}:p})}));};
'''
    a=a.replace(marker,batching+marker,1)
old_listener="    off.push(listen<any>('render-progress',e=>patchProject(e.payload.id,compactPayload(e.payload))));"
new_listener="    off.push(listen<any>('render-progress',e=>{const p=e.payload;if(!p?.id)return;progressPending.set(p.id,p);if(progressTimer===undefined)progressTimer=window.setTimeout(flushRenderProgress,50)}));"
if old_listener in a:a=a.replace(old_listener,new_listener,1)
a=a.replace('disposed=true;if(updateTimer)window.clearTimeout(updateTimer);if(updateInterval)window.clearInterval(updateInterval);', 'disposed=true;if(updateTimer)window.clearTimeout(updateTimer);if(updateInterval)window.clearInterval(updateInterval);if(progressTimer!==undefined)window.clearTimeout(progressTimer);progressPending.clear();',1)
must('window.setTimeout(flushRenderProgress,50)' in a,'render-progress batching missing')
p.write_text(a,encoding='utf-8')

# ---------------------------------------------------------------------------
# Chroma controls: expose real despill and use a useful default for new presets.
# ---------------------------------------------------------------------------
p=Path('src/pages/Editors.tsx'); e=p.read_text(encoding='utf-8')
e=e.replace('  despill: 0,','  despill: 0.35,',1)
e=e.replace("similarity: 0.10, blend: 0.06, saturation: 1, despill: 0", "similarity: 0.10, blend: 0.06, saturation: 1, despill: 0.35")
slider='<SmallRange label="Despill / убрать зелёный ореол" value={current.despill} min={0} max={1} step={0.01} onChange={(value) => patch({ despill: value })} />'
blend='<SmallRange label="Blend / мягкость края" value={current.blend} min={0.001} max={0.35} step={0.001} onChange={(value) => patch({ blend: value })} />'
# Effects and Subscribe each contain the Blend control; insert after both.
if slider not in e:
    e=e.replace(blend,blend+'\n            '+slider)
must(e.count('Despill / убрать зелёный ореол')>=2,'despill slider missing in Effects/Subscribe')
p.write_text(e,encoding='utf-8')

# ---------------------------------------------------------------------------
# WebGL Preview: same despill logic as render, still driven by requestAnimationFrame.
# ---------------------------------------------------------------------------
p=Path('src/components/LiveCompositePreview.tsx'); l=p.read_text(encoding='utf-8')
old_shader="gl.shaderSource(fs,`precision mediump float;varying vec2 v;uniform sampler2D tex;uniform vec3 key;uniform float sim;uniform float blend;uniform float mode;uniform float lthr;uniform float ltol;void main(){vec4 px=texture2D(tex,v);vec3 c=px.rgb;float a=px.a;if(mode<.5){float d=distance(c,key)/1.7320508;float lo=max(0.,sim);float hi=min(1.,lo+max(.001,blend));a*=smoothstep(lo,hi,d);}else if(mode<1.5){float l=dot(c,vec3(.2126,.7152,.0722));float lo=max(0.,lthr-ltol);float hi=min(1.,lthr+ltol);a*=smoothstep(lo,hi,l);}gl_FragColor=vec4(c,a);}`);"
new_shader="gl.shaderSource(fs,`precision mediump float;varying vec2 v;uniform sampler2D tex;uniform vec3 key;uniform float sim;uniform float blend;uniform float dsp;uniform float mode;uniform float lthr;uniform float ltol;void main(){vec4 px=texture2D(tex,v);vec3 c=px.rgb;float a=px.a;if(mode<.5){float d=distance(c,key)/1.7320508;float lo=max(0.,sim);float hi=min(1.,lo+max(.001,blend));a*=smoothstep(lo,hi,d);if(key.g>=key.b){float sp=max(0.,c.g-max(c.r,c.b));c.g=max(0.,c.g-sp*dsp);c.r=min(1.,c.r+sp*dsp*.08);c.b=min(1.,c.b+sp*dsp*.12);}else{float sp=max(0.,c.b-max(c.r,c.g));c.b=max(0.,c.b-sp*dsp);c.r=min(1.,c.r+sp*dsp*.08);c.g=min(1.,c.g+sp*dsp*.12);}}else if(mode<1.5){float l=dot(c,vec3(.2126,.7152,.0722));float lo=max(0.,lthr-ltol);float hi=min(1.,lthr+ltol);a*=smoothstep(lo,hi,l);}gl_FragColor=vec4(c,a);}`);"
if old_shader in l:l=l.replace(old_shader,new_shader,1)
l=l.replace("uBlend=gl.getUniformLocation(program,'blend'),uMode=", "uBlend=gl.getUniformLocation(program,'blend'),uDsp=gl.getUniformLocation(program,'dsp'),uMode=",1)
l=l.replace("gl.uniform1f(uBlend,Math.max(.001,Math.min(.35,e.blend)));gl.uniform1f(uMode", "gl.uniform1f(uBlend,Math.max(.001,Math.min(.35,e.blend)));gl.uniform1f(uDsp,Math.max(0,Math.min(1,e.despill||0)));gl.uniform1f(uMode",1)
must("uniform float dsp" in l and 'gl.uniform1f(uDsp' in l,'WebGL chroma despill missing')
p.write_text(l,encoding='utf-8')

# ---------------------------------------------------------------------------
# Mac compositor hints only; no visual design/layout change.
# ---------------------------------------------------------------------------
p=Path('src/styles.css'); css=p.read_text(encoding='utf-8')
perf='''\n/* ENDLUME 8.39 macOS compositor hints — no visual/layout changes. */\n.pageScene,.liveComposite,.liveGpuOverlay,.liveOverlayCanvas{transform:translateZ(0);backface-visibility:hidden;}\n.queueCard{content-visibility:auto;contain:layout paint style;contain-intrinsic-size:86px;}\n'''
if 'ENDLUME 8.39 macOS compositor hints' not in css:css+=perf
p.write_text(css,encoding='utf-8')

# Preserve the 8.38 no-bars contract explicitly.
r=Path('src-tauri/src/render.rs').read_text(encoding='utf-8')
must('force_original_aspect_ratio=increase' in r and 'crop={}:{}:(iw-ow)/2:(ih-oh)/2' in r,'8.38 YouTube Fill was altered')
must('pad={}:{}' not in r,'black-bar pad returned')

print('ENDLUME alpha.8.39 targeted performance/fidelity patch applied')
