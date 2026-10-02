use crate::{cache,model::{EffectPreset,SubscribePreset}};
use std::path::{Path,PathBuf};
use tauri::{AppHandle,Manager};
use tauri_plugin_shell::ShellExt;

const IMAGE:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];
const VIDEO:&[&str]=&["mp4","mov","m4v","mkv","webm","avi","wmv","flv","ts","mts","m2ts","mpg","mpeg","vob","3gp"];
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
fn overlay_effect(graph:&mut String,base:&mut String,input:usize,e:&EffectPreset,w:u32,h:u32){
  let fx=format!("fx{input}");let next=format!("b{input}");let (scale,x,y)=overlay_geometry(e,w,h);let opacity=effect_opacity(e);
  if e.mode=="screen"||e.mode=="screen-cache"{
    graph.push_str(&format!(";[{base}]format=gbrp[base{input}];[{input}:v]fps=30,format=gbrp,{scale},pad={w}:{h}:'{x}':'{y}':color=black,setsar=1[{fx}];[base{input}][{fx}]blend=all_mode=screen:all_opacity={opacity}[{next}]"));
  }else{
    let prep=if e.mode=="luma"{
      format!("[{input}:v]fps=30,format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08",e.luma_threshold,e.luma_tolerance)
    }else{
      let (similarity,blend)=cache::chromakey_params_859(e);
      let kind=cache::despill_type(&e.key_color);
      let mix=e.despill.clamp(0.0,1.0);
      if cache::is_round_equalizer_859(e){
        format!("[{input}:v]fps=30,format=rgba,colorkey={}:{}:{},{scale},despill=type={kind}:mix={mix}:expand=0.20",color(&e.key_color),similarity,blend)
      }else{
        format!("[{input}:v]fps=30,format=rgba,colorkey={}:{}:{},despill=type={kind}:mix={mix}:expand=0.20",color(&e.key_color),similarity,blend)
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
pub async fn generate_preview(app:AppHandle,project_path:String,time_sec:f64,effects:Vec<EffectPreset>,subscribes:Vec<SubscribePreset>)->Result<String,String>{
  let dir=PathBuf::from(&project_path);if !dir.is_dir(){return Err("Сначала выберите папку проекта".into())}
  let mut media:Vec<PathBuf>=std::fs::read_dir(&dir).map_err(|e|e.to_string())?.flatten().map(|e|e.path()).filter(|p|p.is_file()&&(IMAGE.contains(&ext(p).as_str())||VIDEO.contains(&ext(p).as_str()))).collect();
  media.sort_by(|a,b|natural_name(a).cmp(&natural_name(b)));
  let (src,local_time)=pick_preview_media(&media,time_sec).ok_or("В проекте нет изображения или видео")?;
  let preview_dir=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("previews-v3");std::fs::create_dir_all(&preview_dir).map_err(|e|e.to_string())?;
  if let Ok(rd)=std::fs::read_dir(&preview_dir){let mut files=rd.flatten().filter_map(|e|e.metadata().ok().and_then(|m|m.modified().ok().map(|t|(t,e.path())))).collect::<Vec<_>>();files.sort_by_key(|x|x.0);if files.len()>12{let remove=files.len()-12;for (_,p) in files.into_iter().take(remove){let _=std::fs::remove_file(p);}}}
  let out=preview_dir.join(format!("endlume-preview-{}.mp4",uuid::Uuid::new_v4()));
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
  if is_image(src){args.extend(vec!["-loop","1","-framerate","60","-i",src.to_string_lossy().as_ref()].into_iter().map(String::from));}else{args.extend(vec!["-stream_loop","-1","-ss",&local_time.max(0.0).to_string(),"-i",src.to_string_lossy().as_ref()].into_iter().map(String::from));}
  let enabled_fx:Vec<EffectPreset>=effects.into_iter().filter(ready_overlay).collect();
  let enabled_sub:Vec<SubscribePreset>=subscribes.into_iter().filter(|s|ready_overlay(&s.effect)).collect();
  for e in &enabled_fx{args.extend(vec!["-stream_loop","-1","-ss",&e.preview_frame_time.max(0.0).to_string(),"-i",e.source.as_str()].into_iter().map(String::from));}
  for s in &enabled_sub{args.extend(vec!["-stream_loop","-1","-ss",&s.effect.preview_frame_time.max(0.0).to_string(),"-i",s.effect.source.as_str()].into_iter().map(String::from));}
  let (w,h)=(1920u32,1080u32);let mut graph=format!("[0:v]scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={w}:{h}:(iw-ow)/2:(ih-oh)/2,fps=30,setsar=1[b0]");let mut base="b0".to_string();let mut idx=1usize;
  for e in &enabled_fx{overlay_effect(&mut graph,&mut base,idx,e,w,h);idx+=1;}
  for s in &enabled_sub{overlay_effect(&mut graph,&mut base,idx,&s.effect,w,h);idx+=1;}
  graph.push_str(&format!(";[{base}]fps=60,format=yuv420p[outv]"));
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t","3.0","-an"].into_iter().map(String::from));
  #[cfg(target_os="macos")]
  args.extend(vec!["-c:v","h264_videotoolbox","-realtime","1","-q:v","100","-b:v","35M","-maxrate","50M","-pix_fmt","yuv420p"].into_iter().map(String::from));
  #[cfg(not(target_os="macos"))]
  args.extend(vec!["-c:v","libx264","-preset","veryfast","-crf","8","-pix_fmt","yuv420p"].into_iter().map(String::from));
  args.extend(vec!["-movflags","+faststart","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  if let Err(hw)=run_preview(&app,args.clone()).await{
    #[cfg(target_os="macos")]
    {
      let mut fallback=args;
      if let Some(pos)=fallback.iter().position(|v|v=="-c:v"){
        let end=(pos+8).min(fallback.len());
        fallback.splice(pos..end,vec!["-c:v".into(),"libx264".into(),"-preset".into(),"ultrafast".into(),"-crf".into(),"18".into(),"-pix_fmt".into(),"yuv420p".into()]);
      }
      let _=std::fs::remove_file(&out);run_preview(&app,fallback).await.map_err(|sw|format!("VideoToolbox preview: {hw}; libx264 fallback: {sw}"))?;
    }
    #[cfg(not(target_os="macos"))]
    {return Err(hw)}
  }
  Ok(out.to_string_lossy().into_owned())
}
