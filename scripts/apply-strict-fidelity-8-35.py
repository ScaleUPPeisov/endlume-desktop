from pathlib import Path
import re


def must(cond, msg):
    if not cond:
        raise SystemExit(f"8.35: {msg}")

# ---------------------------------------------------------------------------
# Strict Fidelity for the dominant ENDLUME shape: 1 still image + music.
# Goals: <= ~1 GB / 2h with typical 320k MP3, <= 1 minute render target on M1,
# and no second lossy generation of the source music.
# ---------------------------------------------------------------------------
p=Path('src-tauri/src/render.rs')
r=p.read_text(encoding='utf-8')

# 1) One long GOP per short master. The previous 2-second GOP inserted a large
# 4K I-frame every two seconds, wasting bits and causing visible mosquito noise
# under the 760k budget. 30fps also gives twice the bits/frame vs persisted 60fps.
pat=r'''fn hybrid_master_seconds\(_s:&RenderSettings\)->f64\{.*?\n\}\n\nasync fn choose_hybrid_encoder'''
replacement=r'''fn hybrid_master_seconds(_s:&RenderSettings)->f64{12.0}

async fn hybrid_master_seconds_for_job(app:&AppHandle,job:&QueueJob)->f64{
  let mut d=hybrid_master_seconds(&job.settings);
  for e in job.effects.iter().filter(|e|e.enabled&&!e.source.trim().is_empty()){
    if let Ok(x)=probe_duration(app,&e.source).await{d=d.max(x.clamp(2.0,60.0));}
  }
  d.clamp(12.0,60.0)
}

fn hybrid_video_kbps(s:&RenderSettings)->u64{match s.width{0..=1920=>620,1921..=2560=>700,_=>780}}

fn hybrid_fidelity_args(s:&RenderSettings,encoder:&str,duration:f64)->Vec<String>{
  // A repeated master needs only one I-frame for its complete cycle. This lets
  // VideoToolbox spend a large burst on the original 4K still while the many
  // unchanged P-frames remain extremely small.
  let frames=(s.fps.max(1) as f64*duration.max(2.0)).round().max(1.0) as u32;
  let g=frames.to_string();
  if encoder=="hevc_videotoolbox"{
    let avg=format!("{}k",hybrid_video_kbps(s));
    vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-b:v",&avg,"-maxrate","12M","-bufsize","64M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }else{
    let x265=format!("keyint={}:min-keyint={}:scenecut=0:open-gop=0",g,g);
    vec!["-c:v","libx265","-preset","ultrafast","-crf","16","-tune","ssim","-x265-params",&x265,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }
}

async fn choose_hybrid_encoder'''
new_r,n=re.subn(pat,replacement,r,count=1,flags=re.S)
must(n==1 or ('-bufsize","64M' in r and 'let frames=(s.fps.max(1) as f64*duration.max(2.0)' in r),'hybrid fidelity block replacement failed')
if n==1:r=new_r

# 2) Strict runtime normalization. Persisted 8.34 settings can still be 4K60 +
# 3s crossfade. For a one-still Smart Repeat project those settings conflict
# with the user's hard requirements, so normalize only the render copy.
old='let mut resolved_job=job.clone();refresh_project_paths(&mut resolved_job);let job=&resolved_job;'
new='''let mut resolved_job=job.clone();refresh_project_paths(&mut resolved_job);
  if smart_repeat_project(&resolved_job){
    if resolved_job.settings.fps>30{emit_warning(app,&resolved_job.project.id,"Strict Fidelity: 60 FPS -> 30 FPS для статичного 4K-проекта. Изображение не меняется, Effects/Subscribe остаются плавными, рендер примерно вдвое легче.");}
    resolved_job.settings.fps=resolved_job.settings.fps.min(30);
    let processed_audio=resolved_job.settings.crossfade_sec>0.01||resolved_job.settings.normalize_lufs||resolved_job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false);
    if processed_audio{emit_warning(app,&resolved_job.project.id,"Strict Fidelity: crossfade/LUFS/ambient отключены для этого рендера — исходный MP3 сохраняется bitstream-copy без повторного кодирования и без раздувания файла ALAC.");}
    resolved_job.settings.crossfade_sec=0.0;
    resolved_job.settings.normalize_lufs=false;
    resolved_job.ambient=None;
  }
  let job=&resolved_job;'''
if old in r:r=r.replace(old,new,1)
must('Strict Fidelity: 60 FPS -> 30 FPS' in r and 'resolved_job.settings.crossfade_sec=0.0' in r,'strict runtime normalization missing')

# 3) Do not silently fall back to a multi-gigabyte ALAC cycle in Strict Fidelity.
old_fallback='''            Err(reason)=>{
              emit_warning(app,&job.project.id,&format!("Точный MP3 stream-copy невозможен ({reason}). Перехожу на ALAC lossless."));
              let (cycle,durations,_cycle_duration)=build_lossless_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
              let final_duration=smart_final_duration(target,&durations,0.0,&job.settings.duration_mode);
              let _=app.emit("engine-profile",json!({"id":job.project.id,"audioOriginal":false,"audioLossless":true,"crossfadeApplied":false}));
              (AudioSource::Loop(cycle),durations,final_duration)
            }'''
new_fallback='''            Err(reason)=>{
              return Err(format!("Strict Fidelity: исходную музыку нельзя сохранить bitstream-copy ({reason}). Для режима <=1 ГБ без потери музыки используй MP3 с одинаковыми sample rate/channel layout."));
            }'''
if old_fallback in r:r=r.replace(old_fallback,new_fallback,1)
must('Strict Fidelity: исходную музыку нельзя сохранить bitstream-copy' in r,'strict MP3 fallback guard missing')

# Guard against regression to the noisy 2-second GOP.
must('let g=(s.fps.max(1)*2).to_string();' not in r,'old 2-second GOP still active')
must('"-bufsize","64M"' in r,'large keyframe buffer missing')
must('hybrid_video_kbps(s:&RenderSettings)->u64{match s.width{0..=1920=>620,1921..=2560=>700,_=>780}}' in r,'strict 2h bitrate budget missing')
p.write_text(r,encoding='utf-8')

# 4) New installations start in the same profile. Existing persisted v2 settings
# are migrated once so the UI matches what the renderer actually does.
p=Path('src/store.ts'); s=p.read_text(encoding='utf-8')
s=s.replace("width:3840,height:2160,fps:60,codec:'h264',bitrateMbps:30,durationHours:2,", "width:3840,height:2160,fps:30,codec:'h265',bitrateMbps:30,durationHours:2,",1)
s=s.replace("durationMode:'whole-track',loopMode:'image',crossfadeSec:3,normalizeLufs:false,", "durationMode:'whole-track',loopMode:'image',crossfadeSec:0,normalizeLufs:false,",1)
old_opts="}),{name:'endlume-1-ui',version:2,partialize:(s)=>({settings:s.settings,lastRoot:s.lastRoot,projects:s.projects})}));"
new_opts="}),{name:'endlume-1-ui',version:3,migrate:(persisted:any)=>{const p=(persisted||{}) as Partial<State>;if(p.settings){p.settings={...p.settings,fps:p.settings.fps===60?30:p.settings.fps,crossfadeSec:0,normalizeLufs:false,codec:'h265'};}return p;},partialize:(s)=>({settings:s.settings,lastRoot:s.lastRoot,projects:s.projects})}));"
if old_opts in s:s=s.replace(old_opts,new_opts,1)
elif "version:3,migrate:" not in s:raise SystemExit('8.35: Zustand migration marker missing')
must("fps:30,codec:'h265'" in s and 'crossfadeSec:0' in s,'new default strict settings missing')
p.write_text(s,encoding='utf-8')

# 5) Explain the rule next to Crossfade instead of silently surprising the user.
p=Path('src/pages/ProjectPage.tsx'); x=p.read_text(encoding='utf-8')
needle="'Выключен. Совместимые MP3 можно сохранить bitstream-copy без повторного кодирования.'"
replacement="'Выключен. Для проекта с 1 изображением Strict Fidelity сохраняет совместимые MP3 bitstream-copy без повторного кодирования и удерживает итог около 1 ГБ.'"
if needle in x:x=x.replace(needle,replacement,1)
p.write_text(x,encoding='utf-8')

print('ENDLUME alpha.8.35 Strict Fidelity speed/size/image/audio patch applied')
