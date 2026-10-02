use crate::{cache,model::{EffectPreset,SubscribePreset}};
use serde_json::Value;
use std::path::{Path,PathBuf};
use tauri::{AppHandle,Manager};
use tauri_plugin_shell::ShellExt;

const IMAGE:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];
const VIDEO:&[&str]=&["mp4","mov","m4v","mkv","webm","avi","wmv","flv","ts","mts","m2ts","mpg","mpeg","vob","3gp"];

#[tauri::command]
pub fn preview_frontend_fixture()->Result<Option<Value>,String>{
  let Some(path)=std::env::var_os("ENDLUME_E2E_FRONTEND_PREVIEW_FIXTURE") else{return Ok(None)};
  let raw=std::fs::read(&path).map_err(|e|format!("frontend Preview fixture read: {e}"))?;
  serde_json::from_slice(&raw).map(Some).map_err(|e|format!("frontend Preview fixture json: {e}"))
}

#[tauri::command]
pub fn preview_frontend_report(payload:Value)->Result<(),String>{
  let path=std::env::var_os("ENDLUME_E2E_FRONTEND_PREVIEW_RESULT").ok_or("frontend Preview result path missing")?;
  std::fs::write(path,serde_json::to_vec_pretty(&payload).map_err(|e|e.to_string())?).map_err(|e|format!("frontend Preview result write: {e}"))
}
fn ext(p:&Path)->String{p.extension().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase()}
fn color(hex:&str)->String{format!("0x{}",hex.trim().trim_start_matches('#').trim_start_matches("0x"))}
fn is_image(p:&Path)->bool{IMAGE.contains(&ext(p).as_str())}
fn ready_overlay(e:&EffectPreset)->bool{e.enabled&&!e.source.trim().is_empty()&&Path::new(&e.source).is_file()}

fn natural_name(p:&PathBuf)->(u64,String){
  let s=p.file_name().and_then(|x|x.to_str()).unwrap_or("").to_lowercase();
  let digits=s.chars().skip_while(|c|!c.is_ascii_digit()).take_while(|c|c.is_ascii_digit()).collect::<String>();
  (digits.parse::<u64>().unwrap_or(u64::MAX),s)
}

fn pick_preview_media(media:&[PathBuf],time_sec:f64)->Option<(&PathBuf,f64)>{
  if media.is_empty(){return None}
  let slot=10.0_f64;let t=time_sec.max(0.0);let idx=((t/slot).floor() as usize)%media.len();Some((&media[idx],t%slot))
}

fn overlay_geometry(e:&EffectPreset,w:u32,h:u32)->(String,String,String){
  if e.fullscreen{
    return (format!("scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0"),"0".into(),"0".into())
  }
  let target_w=((w as f64)*e.scale.clamp(0.05,1.5)).round().max(2.0) as u32;
  let target_w=if target_w%2==0{target_w}else{target_w+1};
  let x=format!("max(0,min(W-w,W*{}-w/2))",e.x.clamp(0.0,1.0));
  let y=format!("max(0,min(H-h,H*{}-h/2))",e.y.clamp(0.0,1.0));
  (format!("scale={target_w}:-2:flags=lanczos"),x,y)
}

fn effect_opacity(e:&EffectPreset)->f64{e.opacity.unwrap_or(1.0).clamp(0.0,1.0)}
fn overlay_effect(graph:&mut String,base:&mut String,input:usize,e:&EffectPreset,w:u32,h:u32,is_subscribe:bool){
  let fx=format!("fx{input}");let next=format!("b{input}");let (scale,x,y)=overlay_geometry(e,w,h);let opacity=effect_opacity(e);
  if e.mode=="screen"||e.mode=="screen-cache"{
    graph.push_str(&format!(";[{base}]format=gbrp[base{input}];[{input}:v]setpts=PTS-STARTPTS,fps=30,format=gbrp,{scale},pad={w}:{h}:'{x}':'{y}':color=black,setsar=1[{fx}];[base{input}][{fx}]blend=all_mode=screen:all_opacity={opacity}[{next}]"));
  }else{
    let prep=if e.mode=="luma"{
      format!("[{input}:v]setpts=PTS-STARTPTS,fps=30,format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08",e.luma_threshold,e.luma_tolerance)
    }else{
      let (similarity,blend)=if is_subscribe{cache::subscribe_chromakey_params_1011(e)}else{cache::chromakey_params_859(e)};
      let kind=cache::despill_type(&e.key_color);
      let mix=e.despill.clamp(0.0,1.0);
      if cache::is_round_equalizer_859(e){
        let pre_target_w=((((w as f64)*e.scale.clamp(0.05,1.5)).round().max(2.0) as u32).saturating_mul(2)).max(2);
        let pre_target_w=if pre_target_w%2==0{pre_target_w}else{pre_target_w+1};
        format!("[{input}:v]setpts=PTS-STARTPTS,fps=30,scale={pre_target_w}:-2:flags=neighbor,format=rgba,colorkey={}:{}:{},{scale},despill=type={kind}:mix={mix}:expand=0.20",color(&e.key_color),similarity,blend)
      }else{
        format!("[{input}:v]setpts=PTS-STARTPTS,fps=30,format=rgba,colorkey={}:{}:{},despill=type={kind}:mix={mix}:expand=0.20",color(&e.key_color),similarity,blend)
      }
    };
    let prepared=if cache::is_round_equalizer_859(e){prep}else{format!("{prep},{scale}")};
    graph.push_str(&format!(";{prepared},colorchannelmixer=aa={opacity}[{fx}];[{base}]format=rgba[base{input}];[base{input}][{fx}]overlay=x='{x}':y='{y}':shortest=1:eof_action=repeat:format=auto[{next}]"));
  }
  *base=next;
}

async fn run_preview(app:&AppHandle,args:Vec<String>)->Result<Vec<u8>,String>{
  let out=app.shell().sidecar("ffmpeg").map_err(|e|format!("FFmpeg preview недоступен: {e}"))?.args(args).output().await.map_err(|e|format!("Не удалось запустить FFmpeg preview: {e}"))?;
  if out.status.success(){Ok(out.stderr)}else{Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
}

#[tauri::command]
pub async fn generate_preview_poster(app:AppHandle,project_path:String,time_sec:f64,effects:Vec<EffectPreset>,subscribes:Vec<SubscribePreset>,request_id:Option<String>)->Result<String,String>{
  let request=request_id.unwrap_or_else(||uuid::Uuid::new_v4().to_string());
  let dir=PathBuf::from(&project_path);if !dir.is_dir(){return Err("Сначала выберите папку проекта".into())}
  let mut media:Vec<PathBuf>=std::fs::read_dir(&dir).map_err(|e|e.to_string())?.flatten().map(|e|e.path()).filter(|p|p.is_file()&&(IMAGE.contains(&ext(p).as_str())||VIDEO.contains(&ext(p).as_str()))).collect();
  media.sort_by(|a,b|natural_name(a).cmp(&natural_name(b)));
  let (src,local_time)=pick_preview_media(&media,time_sec).ok_or("В проекте нет изображения или видео")?;
  let preview_dir=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("previews-v3");std::fs::create_dir_all(&preview_dir).map_err(|e|e.to_string())?;
  let id=uuid::Uuid::new_v4();let out=preview_dir.join(format!("endlume-poster-{id}.png"));let tmp=preview_dir.join(format!(".endlume-poster-{id}.tmp.png"));
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
  if is_image(src){args.extend(vec!["-loop","1","-framerate","30","-i",src.to_string_lossy().as_ref()].into_iter().map(String::from));}else{args.extend(vec!["-stream_loop","-1","-ss",&local_time.max(0.0).to_string(),"-i",src.to_string_lossy().as_ref()].into_iter().map(String::from));}
  let enabled_fx:Vec<EffectPreset>=effects.into_iter().filter(ready_overlay).collect();
  let enabled_sub:Vec<SubscribePreset>=subscribes.into_iter().filter(|x|ready_overlay(&x.effect)).collect();
  for e in &enabled_fx{args.extend(vec!["-stream_loop","-1","-ss",&e.preview_frame_time.max(0.0).to_string(),"-i",e.source.as_str()].into_iter().map(String::from));}
  for x in &enabled_sub{let seek=x.effect.preview_frame_time.max(0.75);args.extend(vec!["-stream_loop","-1","-ss",&seek.to_string(),"-i",x.effect.source.as_str()].into_iter().map(String::from));}
  let (w,h)=(960u32,540u32);
  let mut graph=format!("[0:v]scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={w}:{h}:(iw-ow)/2:(ih-oh)/2,fps=30,setsar=1[b0]");
  let mut base="b0".to_string();let mut idx=1usize;
  for e in &enabled_fx{overlay_effect(&mut graph,&mut base,idx,e,w,h,false);idx+=1;}
  for x in &enabled_sub{overlay_effect(&mut graph,&mut base,idx,&x.effect,w,h,true);idx+=1;}
  graph.push_str(&format!(";[{base}]format=rgb24[outv]"));
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-frames:v","1","-compression_level","1","-y",tmp.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_preview(&app,args).await?;
  let size=std::fs::metadata(&tmp).map_err(|e|format!("Preview poster metadata: {e}"))?.len();
  if size<1024{let _=std::fs::remove_file(&tmp);return Err(format!("Preview poster слишком мал: {size} bytes"))}
  std::fs::rename(&tmp,&out).map_err(|e|format!("Preview poster atomic publish: {e}"))?;
  if cfg!(debug_assertions)||std::env::var_os("ENDLUME_PREVIEW_DIAG").is_some(){
    eprintln!("PREVIEW_REQUEST_ID={request}");
    eprintln!("PREVIEW_TYPE={}",if !enabled_sub.is_empty(){"Subscribe"}else if !enabled_fx.is_empty(){"Effects"}else{"Baseline"});
    eprintln!("COMPOSED_POSTER_PATH={}",out.display());
    eprintln!("COMPOSED_POSTER_EXISTS={}",out.is_file());
    eprintln!("COMPOSED_POSTER_BYTES={size}");
    eprintln!("POSTER_WIDTH={w}");
    eprintln!("POSTER_HEIGHT={h}");
  }
  Ok(out.to_string_lossy().into_owned())
}

#[tauri::command]
pub async fn generate_preview(app:AppHandle,project_path:String,time_sec:f64,effects:Vec<EffectPreset>,subscribes:Vec<SubscribePreset>,request_id:Option<String>)->Result<String,String>{
  let request=request_id.unwrap_or_else(||uuid::Uuid::new_v4().to_string());
  let started=std::time::Instant::now();
  let dir=PathBuf::from(&project_path);if !dir.is_dir(){return Err("Сначала выберите папку проекта".into())}
  let mut media:Vec<PathBuf>=std::fs::read_dir(&dir).map_err(|e|e.to_string())?.flatten().map(|e|e.path()).filter(|p|p.is_file()&&(IMAGE.contains(&ext(p).as_str())||VIDEO.contains(&ext(p).as_str()))).collect();
  media.sort_by(|a,b|natural_name(a).cmp(&natural_name(b)));
  let (src,local_time)=pick_preview_media(&media,time_sec).ok_or("В проекте нет изображения или видео")?;
  let preview_dir=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("previews-v3");std::fs::create_dir_all(&preview_dir).map_err(|e|e.to_string())?;
  if let Ok(rd)=std::fs::read_dir(&preview_dir){
    for entry in rd.flatten(){
      let old=entry.metadata().ok().and_then(|m|m.modified().ok()).and_then(|t|t.elapsed().ok()).map(|x|x.as_secs()>600).unwrap_or(false);
      if old{let _=std::fs::remove_file(entry.path());}
    }
  }
  let id=uuid::Uuid::new_v4();
  let out=preview_dir.join(format!("endlume-preview-{id}.mp4"));
  let tmp=preview_dir.join(format!(".endlume-preview-{id}.tmp.mp4"));
  eprintln!("ENDLUME_PREVIEW REQUEST_ID={request} PHASE=START TEMP_FILE={} WIDTH=1920 HEIGHT=1080 PIX_FMT=yuv420p",tmp.display());
  let mut base_args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
  if is_image(src){base_args.extend(vec!["-loop","1","-framerate","60","-i",src.to_string_lossy().as_ref()].into_iter().map(String::from));}else{base_args.extend(vec!["-stream_loop","-1","-ss",&local_time.max(0.0).to_string(),"-i",src.to_string_lossy().as_ref()].into_iter().map(String::from));}
  let enabled_fx:Vec<EffectPreset>=effects.into_iter().filter(ready_overlay).collect();
  let enabled_sub:Vec<SubscribePreset>=subscribes.into_iter().filter(|s|ready_overlay(&s.effect)).collect();
  for e in &enabled_fx{base_args.extend(vec!["-stream_loop","-1","-ss",&e.preview_frame_time.max(0.0).to_string(),"-i",e.source.as_str()].into_iter().map(String::from));}
  for s in &enabled_sub{let seek=s.effect.preview_frame_time.max(0.75);base_args.extend(vec!["-stream_loop","-1","-ss",&seek.to_string(),"-i",s.effect.source.as_str()].into_iter().map(String::from));}
  let (w,h)=(1920u32,1080u32);let mut graph=format!("[0:v]scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={w}:{h}:(iw-ow)/2:(ih-oh)/2,fps=30,setsar=1[b0]");let mut base="b0".to_string();let mut idx=1usize;
  for e in &enabled_fx{overlay_effect(&mut graph,&mut base,idx,e,w,h,false);idx+=1;}
  for s in &enabled_sub{overlay_effect(&mut graph,&mut base,idx,&s.effect,w,h,true);idx+=1;}
  graph.push_str(&format!(";[{base}]fps=60,format=yuv420p[outv]"));
  base_args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t","3.0","-an"].into_iter().map(String::from));

  #[cfg(target_os="macos")]
  let primary_codec=vec!["-c:v","h264_videotoolbox","-realtime","1","-q:v","100","-b:v","35M","-maxrate","50M","-g","1","-bf","0","-pix_fmt","yuv420p"].into_iter().map(String::from).collect::<Vec<_>>();
  #[cfg(not(target_os="macos"))]
  let primary_codec=vec!["-c:v","libx264","-preset","veryfast","-crf","8","-g","1","-keyint_min","1","-sc_threshold","0","-bf","0","-pix_fmt","yuv420p"].into_iter().map(String::from).collect::<Vec<_>>();

  let mut primary=base_args.clone();primary.extend(primary_codec);primary.extend(vec!["-fps_mode","cfr","-r","60","-video_track_timescale","60000","-movflags","+faststart","-y",tmp.to_string_lossy().as_ref()].into_iter().map(String::from));
  if let Err(hw)=run_preview(&app,primary).await{
    #[cfg(target_os="macos")]
    {
      let _=std::fs::remove_file(&tmp);
      let mut fallback=base_args;
      fallback.extend(vec!["-c:v","libx264","-preset","ultrafast","-crf","12","-g","1","-keyint_min","1","-sc_threshold","0","-bf","0","-pix_fmt","yuv420p"].into_iter().map(String::from));
      fallback.extend(vec!["-fps_mode","cfr","-r","60","-video_track_timescale","60000","-movflags","+faststart","-y",tmp.to_string_lossy().as_ref()].into_iter().map(String::from));
      run_preview(&app,fallback).await.map_err(|sw|{let _=std::fs::remove_file(&tmp);format!("VideoToolbox preview: {hw}; libx264 fallback: {sw}")})?;
    }
    #[cfg(not(target_os="macos"))]
    {let _=std::fs::remove_file(&tmp);return Err(hw)}
  }
  let size=std::fs::metadata(&tmp).map_err(|e|format!("Preview temp metadata: {e}"))?.len();
  if size<1024{let _=std::fs::remove_file(&tmp);return Err(format!("Preview temp слишком мал: {size} bytes"))}
  std::fs::rename(&tmp,&out).map_err(|e|format!("Preview atomic publish: {e}"))?;
  crate::live_preview::validate_video_proxy(&app,&out).await.map_err(|e|format!("Exact Preview decode validation: {e}"))?;
  let (frame_width,frame_height,_)=crate::live_preview::frame_probe_diag(&app,&out).await;
  let preview_type=if !enabled_sub.is_empty(){"Subscribe"}else if !enabled_fx.is_empty(){"Effects"}else{"Baseline"};
  if cfg!(debug_assertions)||std::env::var_os("ENDLUME_PREVIEW_DIAG").is_some(){
    eprintln!("PREVIEW_REQUEST_ID={request}");
    eprintln!("PREVIEW_TYPE={preview_type}");
    eprintln!("SOURCE_IMAGE={}",src.display());
    eprintln!("COMPOSED_FRAME_PATH={}",out.display());
    eprintln!("COMPOSED_FRAME_EXISTS={}",out.is_file());
    eprintln!("COMPOSED_FRAME_BYTES={size}");
    eprintln!("FFMPEG_EXIT=0");
    eprintln!("DECODE_VALIDATION=GREEN");
    eprintln!("FRAME_WIDTH={frame_width}");
    eprintln!("FRAME_HEIGHT={frame_height}");
  }
  eprintln!("ENDLUME_PREVIEW REQUEST_ID={request} PHASE=FINISH TEMP_FILE={} PUBLISHED_FILE={} WIDTH={} HEIGHT={} PIX_FMT=yuv420p BUFFER_SIZE={} ELAPSED_MS={}",tmp.display(),out.display(),frame_width,frame_height,size,started.elapsed().as_millis());
  Ok(out.to_string_lossy().into_owned())
}
