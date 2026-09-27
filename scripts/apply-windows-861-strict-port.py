#!/usr/bin/env python3
from pathlib import Path

path = Path('src-tauri/src/render.rs')
s = path.read_text(encoding='utf-8')
marker = 'ENDLUME_WINDOWS_861_STRICT_ENCODERS'
if marker in s:
    print('Windows 8.61 strict encoder port already applied')
    raise SystemExit(0)

def replace_once(old: str, new: str, label: str) -> None:
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected exactly one source block, found {n}')
    s = s.replace(old, new, 1)

replace_once(
'''async fn choose_fidelity_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {
    if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}
  }
  "libx265".into()
}

fn fidelity_video_args(encoder:&str,s:&RenderSettings)->Vec<String>{
  let g=(s.fps.max(1)*10).to_string();
  let raw:Vec<&str>=match encoder{
    "hevc_videotoolbox"=>vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-q:v","95","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"],
    "h264_videotoolbox"=>vec!["-c:v","h264_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-q:v","95","-g",&g,"-pix_fmt","yuv420p"],
    "libx265"=>vec!["-c:v","libx265","-preset","ultrafast","-crf","14","-tune","ssim","-g",&g,"-pix_fmt","yuv420p"],
    _=>vec!["-c:v","libx264","-preset","ultrafast","-crf","12","-tune","stillimage","-g",&g,"-keyint_min",&g,"-sc_threshold","0","-pix_fmt","yuv420p"],
  };
  raw.into_iter().map(String::from).collect()
}
''',
'''async fn choose_fidelity_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {
    if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}
  }
  #[cfg(target_os="windows")]
  {
    if attempt==1{
      for encoder in ["hevc_nvenc","hevc_qsv","hevc_amf"]{
        if encoder_works(app,encoder).await{return encoder.into()}
      }
    }
  }
  "libx265".into()
}

fn fidelity_video_args(encoder:&str,s:&RenderSettings)->Vec<String>{
  let g=(s.fps.max(1)*10).to_string();
  let raw:Vec<&str>=match encoder{
    "hevc_videotoolbox"=>vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-q:v","95","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"],
    "h264_videotoolbox"=>vec!["-c:v","h264_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-q:v","95","-g",&g,"-pix_fmt","yuv420p"],
    "hevc_nvenc"=>vec!["-c:v","hevc_nvenc","-preset","p4","-rc","vbr","-cq","18","-b:v","0","-maxrate","12M","-bufsize","64M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"],
    "hevc_qsv"=>vec!["-c:v","hevc_qsv","-global_quality","18","-maxrate","12M","-bufsize","64M","-g",&g,"-tag:v","hvc1","-pix_fmt","nv12"],
    "hevc_amf"=>vec!["-c:v","hevc_amf","-quality","balanced","-rc","vbr_peak","-qp_i","18","-maxrate","12M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"],
    "libx265"=>vec!["-c:v","libx265","-preset","ultrafast","-crf","14","-tune","ssim","-g",&g,"-pix_fmt","yuv420p"],
    _=>vec!["-c:v","libx264","-preset","ultrafast","-crf","12","-tune","stillimage","-g",&g,"-keyint_min",&g,"-sc_threshold","0","-pix_fmt","yuv420p"],
  };
  raw.into_iter().map(String::from).collect()
}
''',
'fidelity encoder block')

replace_once(
'''fn hybrid_fidelity_args(s:&RenderSettings,encoder:&str,duration:f64)->Vec<String>{
  let frames=(s.fps.max(1) as f64*duration.max(2.0)).round().max(1.0) as u32;
  let g=if encoder=="hevc_videotoolbox"{frames.min(STRICT_857_MAX_GOP_FRAMES)}else{frames}.to_string();
  if encoder=="libx265"{
    let x265=format!("keyint={}:min-keyint={}:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0",g,g);
    vec!["-c:v","libx265","-preset","ultrafast","-crf","18","-maxrate","500k","-bufsize","4M","-x265-params",&x265,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }else{
    vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }
}

async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  if encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  "libx265".into()
}
''',
'''fn hybrid_fidelity_args(s:&RenderSettings,encoder:&str,duration:f64)->Vec<String>{
  let frames=(s.fps.max(1) as f64*duration.max(2.0)).round().max(1.0) as u32;
  let hw_g=frames.min(STRICT_857_MAX_GOP_FRAMES).to_string();
  let sw_g=frames.to_string();
  match encoder{
    "libx265"=>{
      let x265=format!("keyint={}:min-keyint={}:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0",sw_g,sw_g);
      vec!["-c:v","libx265","-preset","ultrafast","-crf","18","-maxrate","500k","-bufsize","4M","-x265-params",&x265,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
    },
    "hevc_nvenc"=>vec!["-c:v","hevc_nvenc","-preset","p4","-rc","vbr","-cq","18","-b:v","500k","-maxrate","12M","-bufsize","64M","-g",&hw_g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect(),
    "hevc_qsv"=>vec!["-c:v","hevc_qsv","-global_quality","18","-maxrate","12M","-bufsize","64M","-g",&hw_g,"-tag:v","hvc1","-pix_fmt","nv12"].into_iter().map(String::from).collect(),
    "hevc_amf"=>vec!["-c:v","hevc_amf","-quality","balanced","-rc","vbr_peak","-b:v","500k","-maxrate","12M","-g",&hw_g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect(),
    "hevc_videotoolbox"=>vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M","-g",&hw_g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect(),
    _=>hybrid_fidelity_args(s,"libx265",duration),
  }
}

async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  #[cfg(target_os="windows")]
  {
    if attempt==1{
      for encoder in ["hevc_nvenc","hevc_qsv","hevc_amf"]{
        if encoder_works(app,encoder).await{return encoder.into()}
      }
    }
  }
  if encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  "libx265".into()
}

// ENDLUME_WINDOWS_861_STRICT_ENCODERS: keep macOS strict semantics intact while
// allowing the exact 8.61 strict pipeline to use Windows HEVC hardware and x265 fallback.
fn strict_856_encoder_allowed(encoder:&str)->bool{
  #[cfg(target_os="macos")]
  {return encoder=="hevc_videotoolbox"}
  #[cfg(target_os="windows")]
  {return matches!(encoder,"hevc_nvenc"|"hevc_qsv"|"hevc_amf"|"libx265")}
  #[cfg(not(any(target_os="macos",target_os="windows")))]
  {encoder=="libx265"}
}
''',
'hybrid strict encoder block')

replace_once(
'''  if !smart_repeat_project(job)||timed_effects(effects,final_duration){return Ok(false)}if subs.iter().any(|x|x.effect.enabled&&!x.effect.source.trim().is_empty()){return Ok(false)}if encoder!="hevc_videotoolbox"{return Err("Strict 8.56: аппаратный HEVC VideoToolbox недоступен; медленный software fallback запрещён".into())}
''',
'''  if !smart_repeat_project(job)||timed_effects(effects,final_duration){return Ok(false)}if subs.iter().any(|x|x.effect.enabled&&!x.effect.source.trim().is_empty()){return Ok(false)}if !strict_856_encoder_allowed(encoder){return Err(format!("Strict 8.61: HEVC encoder {encoder} не разрешён strict pipeline"))}
''',
'strict zero-copy encoder guard')

replace_once(
'''  let max_attempts=if smart_repeat_project(job){1}else{2};
  for attempt in 1..=max_attempts{
    if cancel.load(Ordering::SeqCst){return Err(CANCELLED.into())}
    let smart_repeat=smart_repeat_project(job);let _=std::fs::remove_file(&out);let encoder=if smart_repeat{let e=choose_hybrid_encoder(app,1).await;if e!="hevc_videotoolbox"{return Err("Strict 8.56: HEVC VideoToolbox недоступен; software fallback отключён".into())}e}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};
''',
'''  let max_attempts=if smart_repeat_project(job){if cfg!(target_os="windows"){2}else{1}}else{2};
  for attempt in 1..=max_attempts{
    if cancel.load(Ordering::SeqCst){return Err(CANCELLED.into())}
    let smart_repeat=smart_repeat_project(job);let _=std::fs::remove_file(&out);let encoder=if smart_repeat{let e=choose_hybrid_encoder(app,attempt).await;if !strict_856_encoder_allowed(&e){return Err(format!("Strict 8.61: HEVC encoder {e} недоступен для strict pipeline"))}e}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};
''',
'render attempt / fallback block')

path.write_text(s, encoding='utf-8')
print('Applied ENDLUME Windows 8.61 strict encoder port')
