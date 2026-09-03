#!/usr/bin/env python3
from pathlib import Path

p=Path('src-tauri/src/render.rs')
s=p.read_text()

old='''const CANCELLED:&str="__ENDLUME_CANCELLED__";\nstatic ENCODER_CACHE:OnceLock<parking_lot::Mutex<HashMap<String,String>>>=OnceLock::new();'''
new='''const CANCELLED:&str="__ENDLUME_CANCELLED__";\nconst HELPER_TIMEOUT_SECS:u64=60;\nconst FFMPEG_STALL_TIMEOUT_SECS:u64=120;\nstatic ENCODER_CACHE:OnceLock<parking_lot::Mutex<HashMap<String,String>>>=OnceLock::new();'''
assert old in s, 'constants marker missing'
s=s.replace(old,new,1)

old='''async fn output(app:&AppHandle,name:&str,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{\n  let out=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;\n  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}\n  Ok((out.stdout,out.stderr))\n}'''
new='''async fn output(app:&AppHandle,name:&str,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{\n  let command=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args);\n  let out=tokio::time::timeout(Duration::from_secs(HELPER_TIMEOUT_SECS),command.output()).await\n    .map_err(|_|format!("{name} не отвечает более {HELPER_TIMEOUT_SECS} сек"))?\n    .map_err(|e|e.to_string())?;\n  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}\n  Ok((out.stdout,out.stderr))\n}\n\nfn ffmpeg_is_stalled(progress_idle:Duration,activity_idle:Duration)->bool{\n  let limit=Duration::from_secs(FFMPEG_STALL_TIMEOUT_SECS);\n  progress_idle>=limit&&activity_idle>=limit\n}'''
assert old in s, 'output() marker missing'
s=s.replace(old,new,1)

old='''  let pid=child.pid();let mut child=Some(child);let mut last=base;let mut stderr_tail=String::new();let mut sys=System::new_all();let mut metric_tick=Instant::now();\n  loop{\n    if cancel.load(Ordering::SeqCst){if let Some(c)=child.take(){let _=c.kill();}return Err(CANCELLED.into())}\n    let event=tokio::time::timeout(Duration::from_millis(160),rx.recv()).await;\n    if metric_tick.elapsed()>=Duration::from_millis(480){'''
new='''  let pid=child.pid();let mut child=Some(child);let mut last=base;let mut stderr_tail=String::new();let mut sys=System::new_all();let mut metric_tick=Instant::now();\n  let mut last_activity=Instant::now();let mut last_progress=Instant::now();let mut last_out_sec=-1.0_f64;\n  loop{\n    if cancel.load(Ordering::SeqCst){if let Some(c)=child.take(){let _=c.kill();}return Err(CANCELLED.into())}\n    let event=tokio::time::timeout(Duration::from_millis(160),rx.recv()).await;\n    if ffmpeg_is_stalled(last_progress.elapsed(),last_activity.elapsed()){\n      emit_progress(app,job,started,timer,last,"FFmpeg не отвечает — останавливаю процесс",encoder,attempt,None);\n      if let Some(c)=child.take(){let _=c.kill();}\n      let tail=stderr_tail.lines().rev().take(8).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\\n");\n      let detail=if tail.trim().is_empty(){String::new()}else{format!("\\nПоследний вывод FFmpeg:\\n{tail}")};\n      return Err(format!("FFmpeg завис на этапе «{stage}»: нет прогресса более {FFMPEG_STALL_TIMEOUT_SECS} сек.{detail}"));\n    }\n    if metric_tick.elapsed()>=Duration::from_millis(480){'''
assert old in s, 'run_ffmpeg init marker missing'
s=s.replace(old,new,1)

old='''      CommandEvent::Stdout(bytes)|CommandEvent::Stderr(bytes)=>{\n        let text=String::from_utf8_lossy(&bytes);stderr_tail.push_str(&text);if stderr_tail.len()>12000{stderr_tail=stderr_tail.split_off(stderr_tail.len()-9000)}\n        for line in text.lines(){\n          let raw=line.strip_prefix("out_time_us=").or_else(||line.strip_prefix("out_time_ms="));\n          if let Some(raw)=raw.and_then(|x|x.parse::<f64>().ok()){\n            let out_sec=raw/1_000_000.0;let frac=if expected_sec>0.0{(out_sec/expected_sec).clamp(0.0,1.0)}else{0.0};let p=base+frac*span;\n            if p-last>=0.01{last=p;emit_progress(app,job,started,timer,p,stage,encoder,attempt,None)}\n          }\n        }\n      },'''
new='''      CommandEvent::Stdout(bytes)|CommandEvent::Stderr(bytes)=>{\n        last_activity=Instant::now();\n        let text=String::from_utf8_lossy(&bytes);stderr_tail.push_str(&text);if stderr_tail.len()>12000{stderr_tail=stderr_tail.split_off(stderr_tail.len()-9000)}\n        for line in text.lines(){\n          let raw=line.strip_prefix("out_time_us=").or_else(||line.strip_prefix("out_time_ms="));\n          if let Some(raw)=raw.and_then(|x|x.parse::<f64>().ok()){\n            let out_sec=raw/1_000_000.0;\n            if out_sec>last_out_sec+0.001{last_out_sec=out_sec;last_progress=Instant::now();}\n            let frac=if expected_sec>0.0{(out_sec/expected_sec).clamp(0.0,1.0)}else{0.0};let p=base+frac*span;\n            if p-last>=0.01{last=p;emit_progress(app,job,started,timer,p,stage,encoder,attempt,None)}\n          }\n          if line.trim()=="progress=end"{last_progress=Instant::now();}\n        }\n      },'''
assert old in s, 'stdout marker missing'
s=s.replace(old,new,1)

old='''async fn verify_result(app:&AppHandle,out:&Path,expected:f64,s:&RenderSettings)->Result<(),String>{let d=probe_duration(app,out.to_string_lossy().as_ref()).await?;'''
new='''async fn verify_result(app:&AppHandle,out:&Path,expected:f64,s:&RenderSettings)->Result<(),String>{let meta=std::fs::metadata(out).map_err(|e|format!("Финальный файл не создан: {e}"))?;if meta.len()<1024{return Err("Финальный файл создан пустым или повреждённым".into())}let d=probe_duration(app,out.to_string_lossy().as_ref()).await?;'''
assert old in s, 'verify marker missing'
s=s.replace(old,new,1)

test='''\n\n#[cfg(test)]\nmod watchdog_tests{\n  use super::*;\n  #[test]\n  fn does_not_timeout_active_ffmpeg(){\n    assert!(!ffmpeg_is_stalled(Duration::from_secs(119),Duration::from_secs(119)));\n    assert!(!ffmpeg_is_stalled(Duration::from_secs(121),Duration::from_secs(1)));\n  }\n  #[test]\n  fn times_out_truly_stalled_ffmpeg(){\n    assert!(ffmpeg_is_stalled(Duration::from_secs(120),Duration::from_secs(120)));\n    assert!(ffmpeg_is_stalled(Duration::from_secs(300),Duration::from_secs(300)));\n  }\n}\n'''
assert 'mod watchdog_tests' not in s
s += test
p.write_text(s)
print('ENDLUME render watchdog patch applied')
