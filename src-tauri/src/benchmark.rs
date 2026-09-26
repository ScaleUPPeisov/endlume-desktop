use serde_json::{json,Value};
use std::{fs,time::Instant};
use tauri::{AppHandle,Manager};
use tauri_plugin_shell::ShellExt;

async fn encoder_list(app:&AppHandle)->Result<String,String>{
  let out=app.shell().sidecar("ffmpeg").map_err(|e|e.to_string())?
    .args(["-hide_banner","-encoders"]).output().await.map_err(|e|e.to_string())?;
  if !out.status.success(){
    return Err(String::from_utf8_lossy(&out.stderr).trim().to_string());
  }
  Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

fn listed(encoders:&str,name:&str)->bool{
  encoders.lines().any(|line|line.split_whitespace().nth(1)==Some(name))
}

fn short_error(bytes:&[u8])->String{
  let text=String::from_utf8_lossy(bytes);
  let lines=text.lines().map(str::trim).filter(|x|!x.is_empty()).collect::<Vec<_>>();
  lines.iter().rev().take(4).rev().copied().collect::<Vec<_>>().join(" • ")
}

async fn functional_test(app:&AppHandle,encoder:&str)->(bool,Option<f64>,String){
  let started=Instant::now();
  let cache=match app.path().app_cache_dir(){Ok(p)=>p.join("benchmark"),Err(e)=>return(false,None,e.to_string())};
  if let Err(e)=fs::create_dir_all(&cache){return(false,None,e.to_string())}
  let ext=if encoder.contains("hevc")||encoder.contains("265"){"hevc.mp4"}else{"h264.mp4"};
  let out_path=cache.join(format!("engine-{}-{}",encoder,ext));
  let _=fs::remove_file(&out_path);

  // Encode a real short MP4 instead of the null muxer. This exercises the same
  // VideoToolbox/libx264 path used by ENDLUME and avoids false negatives from
  // encoders/muxers that behave differently when no real output container exists.
  let mut args=vec![
    "-hide_banner".to_string(),"-loglevel".to_string(),"error".to_string(),
    "-f".to_string(),"lavfi".to_string(),"-i".to_string(),"testsrc2=size=640x360:rate=30".to_string(),
    "-frames:v".to_string(),"30".to_string(),"-an".to_string(),"-c:v".to_string(),encoder.to_string(),
  ];
  if encoder.contains("videotoolbox"){
    args.extend(["-realtime","1","-allow_sw","1"].into_iter().map(String::from));
  }
  if encoder.starts_with("h264_")||encoder=="libx264"{
    args.extend(["-pix_fmt","yuv420p"].into_iter().map(String::from));
  }
  if encoder.contains("hevc")||encoder=="libx265"{
    args.extend(["-pix_fmt","yuv420p","-tag:v","hvc1"].into_iter().map(String::from));
  }
  args.extend(["-movflags","+faststart","-y"].into_iter().map(String::from));
  args.push(out_path.to_string_lossy().into_owned());

  let result=match app.shell().sidecar("ffmpeg").map_err(|e|e.to_string()){
    Ok(cmd)=>cmd.args(args).output().await,
    Err(e)=>return(false,None,e),
  };
  match result{
    Ok(out) if out.status.success()=>{
      let valid=fs::metadata(&out_path).map(|m|m.len()>1024).unwrap_or(false);
      let _=fs::remove_file(&out_path);
      if valid{(true,Some(started.elapsed().as_secs_f64()),"Работает".into())}
      else{(false,None,"FFmpeg завершился без ошибки, но тестовый файл не создан".into())}
    }
    Ok(out)=>{
      let _=fs::remove_file(&out_path);
      let note=short_error(&out.stderr);
      (false,None,if note.is_empty(){format!("FFmpeg exit status: {:?}",out.status)}else{note})
    }
    Err(e)=>{let _=fs::remove_file(&out_path);(false,None,e.to_string())}
  }
}

#[tauri::command]
pub async fn benchmark_engine(app:AppHandle)->Value{
  #[cfg(target_os="macos")]
  let names=vec!["hevc_videotoolbox","libx265"];
  #[cfg(target_os="windows")]
  let names=vec!["hevc_nvenc","hevc_qsv","hevc_amf","libx265"];
  #[cfg(not(any(target_os="macos",target_os="windows")))]
  let names=vec!["libx265"];

  let list=encoder_list(&app).await;
  let list_error=list.as_ref().err().cloned();
  let encoders=list.unwrap_or_default();
  let mut rows=Vec::new();
  let mut selected:Option<String>=None;
  let mut best=f64::MAX;

  for name in names{
    let is_listed=listed(&encoders,name);
    if !is_listed{
      rows.push(json!({"encoder":name,"ok":false,"listed":false,"seconds":null,"note":list_error.clone().unwrap_or_else(||"Кодировщик отсутствует в комплектном FFmpeg".into())}));
      continue;
    }
    let (ok,seconds,note)=functional_test(&app,name).await;
    if ok{
      if let Some(s)=seconds{
        if s<best{best=s;selected=Some(name.to_string());}
      }
    }
    rows.push(json!({"encoder":name,"ok":ok,"listed":true,"seconds":seconds,"note":note}));
  }

  let successful=rows.iter().filter(|x|x.get("ok").and_then(|v|v.as_bool())==Some(true)).count();
  json!({
    "selected":selected,
    "candidates":rows,
    "successful":successful,
    "platform":std::env::consts::OS,
    "arch":std::env::consts::ARCH,
    "ffmpegProbeOk":list_error.is_none(),
    "ffmpegProbeError":list_error
  })
}
