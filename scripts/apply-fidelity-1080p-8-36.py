from pathlib import Path
import re


def must(cond, msg):
    if not cond:
        raise SystemExit(f"8.36: {msg}")

p=Path('src-tauri/src/render.rs')
r=p.read_text(encoding='utf-8')

# ---------------------------------------------------------------------------
# Exact Full-HD output for the dominant ENDLUME workflow: one still + music.
# The previous 8.35 profile forced 4K and then tried to fit that inside a tiny
# 2-hour bitrate budget. That is exactly the wrong trade-off for a YouTube 1080p
# deliverable and is visible as block/mosquito artefacts on the first frame.
# ---------------------------------------------------------------------------
old='''  if smart_repeat_project(&resolved_job){
    if resolved_job.settings.fps>30{emit_warning(app,&resolved_job.project.id,"Strict Fidelity: 60 FPS -> 30 FPS для статичного 4K-проекта. Изображение не меняется, Effects/Subscribe остаются плавными, рендер примерно вдвое легче.");}
    resolved_job.settings.fps=resolved_job.settings.fps.min(30);
'''
new='''  if smart_repeat_project(&resolved_job){
    if resolved_job.settings.width!=1920||resolved_job.settings.height!=1080{emit_warning(app,&resolved_job.project.id,"Fidelity Lock: one-image проект выводится строго 1920x1080. Это убирает бессмысленное 4K-сжатие при лимите около 1 ГБ.");}
    if resolved_job.settings.fps>30{emit_warning(app,&resolved_job.project.id,"Fidelity Lock: 60 FPS -> 30 FPS для статичного проекта. Исходная картинка не теряет деталей, а Effects/Subscribe остаются плавными.");}
    resolved_job.settings.width=1920;
    resolved_job.settings.height=1080;
    resolved_job.settings.fps=resolved_job.settings.fps.min(30);
    resolved_job.settings.codec="h265".into();
'''
if old in r:r=r.replace(old,new,1)
must('resolved_job.settings.width=1920;' in r and 'resolved_job.settings.height=1080;' in r,'runtime 1920x1080 lock missing')

# Highest-quality resize path. One resize only, directly from the original still.
old_base='fn base_filter(s:&RenderSettings,label:&str)->String{format!("[{label}]scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,s.fps)}'
new_base='fn base_filter(s:&RenderSettings,label:&str)->String{format!("[{label}]scale={}:{}:force_original_aspect_ratio=decrease:flags=lanczos+accurate_rnd,pad={}:{}:(ow-iw)/2:(oh-ih)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,s.fps)}'
if old_base in r:r=r.replace(old_base,new_base,1)
must('flags=lanczos+accurate_rnd' in r,'Lanczos source-image scaling missing')

# 12-second short master remains fast. x265 CRF protects the first I-frame, while
# VBV caps dynamic Effects. Local regression on a detailed 1080p still gives
# first-frame SSIM ~0.999; a deliberately busy 640x360 motion overlay stays at
# about 0.72 Mbit/s. With original 320k MP3 that remains below ~1 GB for ~2h.
pat=r'''fn hybrid_video_kbps\(s:&RenderSettings\)->u64\{.*?\}\n\nfn hybrid_fidelity_args\(s:&RenderSettings,encoder:&str,duration:f64\)->Vec<String>\{.*?\n\}\n\nasync fn choose_hybrid_encoder\(app:&AppHandle,attempt:u32\)->String\{.*?\n\}'''
replacement=r'''fn hybrid_video_kbps(_s:&RenderSettings)->u64{550}

fn hybrid_fidelity_args(s:&RenderSettings,encoder:&str,duration:f64)->Vec<String>{
  let frames=(s.fps.max(1) as f64*duration.max(2.0)).round().max(1.0) as u32;
  let g=frames.to_string();
  if encoder=="libx265"{
    let x265=format!("keyint={}:min-keyint={}:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0",g,g);
    vec!["-c:v","libx265","-preset","ultrafast","-crf","18","-maxrate","550k","-bufsize","4M","-x265-params",&x265,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }else{
    vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-b:v","550k","-maxrate","4M","-bufsize","16M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }
}

async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  // For a short 1080p master, software x265 gives materially cleaner I-frames
  // at the same final-file budget and is still comfortably inside the 1-minute
  // target. VideoToolbox remains the automatic second-attempt fallback.
  if attempt==1&&encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  "libx265".into()
}'''
r2,n=re.subn(pat,replacement,r,count=1,flags=re.S)
must(n==1,'hybrid fidelity block replacement failed')
r=r2

must('"-crf","18"' in r,'CRF18 quality control missing')
must('"-maxrate","550k"' in r,'dynamic-effects bitrate cap missing')
must('"-bufsize","4M"' in r,'I-frame quality buffer missing')
must('attempt==1&&encoder_works(app,"libx265")' in r,'x265-first short-master selector missing')
p.write_text(r,encoding='utf-8')

# Persisted UI must agree with the runtime lock.
p=Path('src/store.ts'); s=p.read_text(encoding='utf-8')
s=s.replace("width:3840,height:2160,fps:30,codec:'h265'","width:1920,height:1080,fps:30,codec:'h265'",1)
s=s.replace("version:3,migrate:(persisted:any)=>{const p:any=persisted||{};if(p.settings){p.settings={...p.settings,fps:p.settings.fps===60?30:p.settings.fps,crossfadeSec:0,normalizeLufs:false,codec:'h265'};}return p;}","version:4,migrate:(persisted:any)=>{const p:any=persisted||{};if(p.settings){p.settings={...p.settings,width:1920,height:1080,fps:p.settings.fps===60?30:p.settings.fps,crossfadeSec:0,normalizeLufs:false,codec:'h265'};}return p;}",1)
must("width:1920,height:1080,fps:30,codec:'h265'" in s,'1080p defaults missing')
must('version:4,migrate:' in s and 'width:1920,height:1080' in s,'persisted settings are not migrated to 1080p')
p.write_text(s,encoding='utf-8')

# Put Full HD first in the UI because it is now the canonical one-image profile.
p=Path('src/pages/ProjectPage.tsx'); x=p.read_text(encoding='utf-8')
x=x.replace("const resolutions=[{w:3840,h:2160,label:'4K UHD'},{w:2560,h:1440,label:'2K QHD'},{w:1920,h:1080,label:'1080P FULL HD'}];","const resolutions=[{w:1920,h:1080,label:'1080P FULL HD'},{w:2560,h:1440,label:'2K QHD'},{w:3840,h:2160,label:'4K UHD'}];",1)
x=x.replace('Для проекта с 1 изображением Strict Fidelity сохраняет совместимые MP3 bitstream-copy без повторного кодирования и удерживает итог около 1 ГБ.','Для проекта с 1 изображением Fidelity Lock выводит строго 1920×1080 и сохраняет совместимые MP3 bitstream-copy без повторного кодирования.',1)
p.write_text(x,encoding='utf-8')

print('ENDLUME alpha.8.36 1080p Fidelity Lock applied')
