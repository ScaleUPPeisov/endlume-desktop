#!/usr/bin/env python3
from pathlib import Path
import re

VERSION='1.0.0-alpha.8.46'
ROOT=Path(__file__).resolve().parent.parent

def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.46: missing {rel}')
    return p

def must(c,m):
    if not c: raise SystemExit('8.46: '+m)

p=need('src-tauri/src/render.rs');s=p.read_text(encoding='utf-8')

# 8.46 is applied after 8.45. Guard the exact fast-finalize baseline first.
for marker in [
    'struct FinalProbe{video_bitrate:Option<u64>}',
    'ffprobe_output_timeout',
    'Duration::from_secs(12)',
    'final-verify',
    'Финализация результата',
    'last_error.starts_with("FINAL_VERIFY:")',
    'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};',
    'fn cfr_output_args(',
    '"-fps_mode".into(),"cfr".into()',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    'materialize_continuous_audio',
    'acrossfade=d={cf}:c1=tri:c2=tri'
]: must(marker in s,'protected 8.45 invariant missing: '+marker)
for bad in ['"-count_packets"','nb_read_packets','let bitrate=probe_video_bitrate(app,&out).await;']:
    must(bad not in s,'slow finalizer returned before watchdog patch: '+bad)

old='const CANCELLED:&str="__ENDLUME_CANCELLED__";\nstatic ENCODER_CACHE:OnceLock<parking_lot::Mutex<HashMap<String,String>>>=OnceLock::new();'
new='const CANCELLED:&str="__ENDLUME_CANCELLED__";\nconst HELPER_TIMEOUT_SECS:u64=60;\nconst FFMPEG_STALL_TIMEOUT_SECS:u64=120;\nstatic ENCODER_CACHE:OnceLock<parking_lot::Mutex<HashMap<String,String>>>=OnceLock::new();'
must(old in s,'render constants marker missing')
s=s.replace(old,new,1)

old='''async fn output(app:&AppHandle,name:&str,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{
  let out=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
  Ok((out.stdout,out.stderr))
}'''
new='''async fn output(app:&AppHandle,name:&str,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{
  let command=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args);
  let out=tokio::time::timeout(Duration::from_secs(HELPER_TIMEOUT_SECS),command.output()).await
    .map_err(|_|format!("{name} не отвечает более {HELPER_TIMEOUT_SECS} сек"))?
    .map_err(|e|e.to_string())?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
  Ok((out.stdout,out.stderr))
}

fn ffmpeg_is_stalled(progress_idle:Duration,activity_idle:Duration)->bool{
  let limit=Duration::from_secs(FFMPEG_STALL_TIMEOUT_SECS);
  progress_idle>=limit&&activity_idle>=limit
}'''
must(old in s,'bounded helper insertion marker missing')
s=s.replace(old,new,1)

old='''  let pid=child.pid();let mut child=Some(child);let mut last=base;let mut stderr_tail=String::new();let mut sys=System::new_all();let mut metric_tick=Instant::now();
  loop{
    if cancel.load(Ordering::SeqCst){if let Some(c)=child.take(){let _=c.kill();}return Err(CANCELLED.into())}
    let event=tokio::time::timeout(Duration::from_millis(160),rx.recv()).await;
    if metric_tick.elapsed()>=Duration::from_millis(480){'''
new='''  let pid=child.pid();let mut child=Some(child);let mut last=base;let mut stderr_tail=String::new();let mut sys=System::new_all();let mut metric_tick=Instant::now();
  let mut last_activity=Instant::now();let mut last_progress=Instant::now();let mut last_out_sec=-1.0_f64;
  loop{
    if cancel.load(Ordering::SeqCst){if let Some(c)=child.take(){let _=c.kill();}return Err(CANCELLED.into())}
    let event=tokio::time::timeout(Duration::from_millis(160),rx.recv()).await;
    if ffmpeg_is_stalled(last_progress.elapsed(),last_activity.elapsed()){
      emit_progress(app,job,started,timer,last,"FFmpeg не отвечает — останавливаю процесс",encoder,attempt,None);
      if let Some(c)=child.take(){let _=c.kill();}
      let tail=stderr_tail.lines().rev().take(8).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join("\\n");
      let detail=if tail.trim().is_empty(){String::new()}else{format!("\\nПоследний вывод FFmpeg:\\n{tail}")};
      return Err(format!("FFmpeg завис на этапе «{stage}»: нет прогресса более {FFMPEG_STALL_TIMEOUT_SECS} сек.{detail}"));
    }
    if metric_tick.elapsed()>=Duration::from_millis(480){'''
must(old in s,'FFmpeg loop marker missing')
s=s.replace(old,new,1)

old='''      CommandEvent::Stdout(bytes)|CommandEvent::Stderr(bytes)=>{
        let text=String::from_utf8_lossy(&bytes);stderr_tail.push_str(&text);if stderr_tail.len()>12000{stderr_tail=stderr_tail.split_off(stderr_tail.len()-9000)}
        for line in text.lines(){
          let raw=line.strip_prefix("out_time_us=").or_else(||line.strip_prefix("out_time_ms="));
          if let Some(raw)=raw.and_then(|x|x.parse::<f64>().ok()){
            let out_sec=raw/1_000_000.0;let frac=if expected_sec>0.0{(out_sec/expected_sec).clamp(0.0,1.0)}else{0.0};let p=base+frac*span;
            if p-last>=0.01{last=p;emit_progress(app,job,started,timer,p,stage,encoder,attempt,None)}
          }
        }
      },'''
new='''      CommandEvent::Stdout(bytes)|CommandEvent::Stderr(bytes)=>{
        last_activity=Instant::now();
        let text=String::from_utf8_lossy(&bytes);stderr_tail.push_str(&text);if stderr_tail.len()>12000{stderr_tail=stderr_tail.split_off(stderr_tail.len()-9000)}
        for line in text.lines(){
          let raw=line.strip_prefix("out_time_us=").or_else(||line.strip_prefix("out_time_ms="));
          if let Some(raw)=raw.and_then(|x|x.parse::<f64>().ok()){
            let out_sec=raw/1_000_000.0;
            if out_sec>last_out_sec+0.001{last_out_sec=out_sec;last_progress=Instant::now();}
            let frac=if expected_sec>0.0{(out_sec/expected_sec).clamp(0.0,1.0)}else{0.0};let p=base+frac*span;
            if p-last>=0.01{last=p;emit_progress(app,job,started,timer,p,stage,encoder,attempt,None)}
          }
          if line.trim()=="progress=end"{last_progress=Instant::now();}
        }
      },'''
must(old in s,'FFmpeg progress marker missing')
s=s.replace(old,new,1)

# Compile-time unit regression for the timeout predicate.
must('mod watchdog_tests' not in s,'watchdog tests already exist unexpectedly')
s+='''

#[cfg(test)]
mod watchdog_tests{
  use super::*;
  #[test]
  fn active_ffmpeg_is_not_stalled(){
    assert!(!ffmpeg_is_stalled(Duration::from_secs(119),Duration::from_secs(119)));
    assert!(!ffmpeg_is_stalled(Duration::from_secs(121),Duration::from_secs(1)));
  }
  #[test]
  fn dead_ffmpeg_is_stalled(){
    assert!(ffmpeg_is_stalled(Duration::from_secs(120),Duration::from_secs(120)));
    assert!(ffmpeg_is_stalled(Duration::from_secs(300),Duration::from_secs(300)));
  }
}
'''

# The existing attempt loop already retries ordinary render errors once using its
# reserve engine. FINAL_VERIFY remains excluded from full re-render by 8.45.
must('if attempt<2{emit_progress(app,job,started,&timer,2.0,"Ошибка рендера — резервный движок",&encoder,attempt+1,None);}' in s,'existing reserve-engine retry contract missing')

p.write_text(s,encoding='utf-8')

# Version identity only; no unrelated feature code is changed.
for rel in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    q=need(rel);t=q.read_text(encoding='utf-8');t=re.sub(r'1\.0\.0-alpha\.8\.\d+',VERSION,t);q.write_text(t,encoding='utf-8')

q=need('src/components/ReleaseHistory.tsx');h=q.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.46',date:'03.09.2026',current:true,title:'Render Stall Guard',items:['FFmpeg больше не может висеть бесконечно: 120 секунд без активности и прогресса → процесс останавливается.','После зависания штатный резервный движок получает один автоматический повтор; повторный сбой завершается понятной ошибкой.','FFprobe/короткие helper-команды ограничены 60 секундами, а быстрый финальный FFprobe 8.45 остаётся ограничен 12 секундами.','Качество, 500k bitrate budget, 30/60 FPS, музыка, Effects/Subscribe, VYRON Bridge и локальный pipeline не изменены.']},
"""
anchor='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.46'" not in h:
    must(anchor in h,'release history anchor missing');h=h.replace(anchor,anchor+entry,1)
q.write_text(h,encoding='utf-8')

# Final invariants.
s=p.read_text(encoding='utf-8')
for marker in ['FFMPEG_STALL_TIMEOUT_SECS:u64=120','HELPER_TIMEOUT_SECS:u64=60','ffmpeg_is_stalled(','last_activity=Instant::now()','last_progress=Instant::now()','FFmpeg не отвечает — останавливаю процесс','нет прогресса более {FFMPEG_STALL_TIMEOUT_SECS} сек','mod watchdog_tests']:
    must(marker in s,'watchdog invariant missing after patch: '+marker)
for marker in ['ffprobe_output_timeout','Duration::from_secs(12)','final-verify','Финализация результата','last_error.starts_with("FINAL_VERIFY:")','fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}']:
    must(marker in s,'8.45 invariant lost after watchdog: '+marker)
print('ENDLUME 8.46 render stall guard: PASS')
