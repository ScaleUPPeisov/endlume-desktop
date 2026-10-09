use serde_json::{json,Value};
use std::time::Instant;
use tauri::AppHandle;
use tauri_plugin_shell::ShellExt;

async fn test(app:&AppHandle,encoder:&str)->(bool,Option<f64>,String){
  let started=Instant::now();
  let args=vec!["-hide_banner","-loglevel","error","-f","lavfi","-i","testsrc2=size=1920x1080:rate=60","-t","0.7","-an","-c:v",encoder,"-f","null","-"];
  match app.shell().sidecar("ffmpeg").and_then(|c|Ok(c.args(args))){
    Ok(cmd)=>match cmd.output().await{Ok(out) if out.status.success()=>(true,Some(started.elapsed().as_secs_f64()),"ok".into()),Ok(out)=>(false,None,String::from_utf8_lossy(&out.stderr).lines().last().unwrap_or("encoder unavailable").to_string()),Err(e)=>(false,None,e.to_string())},
    Err(e)=>(false,None,e.to_string())
  }
}

#[tauri::command]
pub async fn benchmark_engine(app:AppHandle)->Value{
  #[cfg(target_os="macos")]
  let names=vec!["h264_videotoolbox","hevc_videotoolbox","libx264"];
  #[cfg(target_os="windows")]
  let names=vec!["h264_nvenc","h264_qsv","h264_amf","libx264"];
  #[cfg(not(any(target_os="macos",target_os="windows")))]
  let names=vec!["libx264"];
  let mut rows=Vec::new();let mut selected="libx264".to_string();let mut best=f64::MAX;
  for name in names{let (ok,seconds,note)=test(&app,name).await;if ok{if let Some(s)=seconds{if s<best{best=s;selected=name.to_string()}}}rows.push(json!({"encoder":name,"ok":ok,"seconds":seconds,"note":note}));}
  json!({"selected":selected,"candidates":rows,"platform":std::env::consts::OS})
}
