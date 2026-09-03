#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def need(rel):
 p=ROOT/rel
 if not p.is_file(): raise SystemExit('8.46-post: missing '+rel)
 return p

def must(c,m):
 if not c: raise SystemExit('8.46-post: '+m)

p=need('src-tauri/src/render.rs');s=p.read_text(encoding='utf-8')
# The main 8.46 migration must already be present.
for m in ['FFMPEG_STALL_TIMEOUT_SECS:u64=120','fn staged_output(','fn cleanup_partial(','fn promote_partial(','last_error.starts_with("FFMPEG_STALL:")']:
 must(m in s,'main 8.46 marker missing: '+m)

# Even short helper FFmpeg commands write via .partial.<ext> and atomically promote.
start=s.find('async fn output(app:&AppHandle,name:&str,args:Vec<String>)')
end=s.find('\n\nfn render_diag_path',start)
must(start>=0 and end>start,'8.46 bounded helper block missing')
new=r'''async fn output(app:&AppHandle,name:&str,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{
  let limit=if name=="ffprobe"{Duration::from_secs(HELPER_FFPROBE_TIMEOUT_SECS)}else{Duration::from_secs(HELPER_FFMPEG_TIMEOUT_SECS)};let (run_args,staged)=if name=="ffmpeg"{staged_output(&args)}else{(args,None)};cleanup_partial(&staged);
  let (mut rx,child)=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(run_args).spawn().map_err(|e|e.to_string())?;let pid=child.pid();let mut child=Some(child);let started=Instant::now();let mut stdout=Vec::new();let mut stderr=Vec::new();
  loop{
    if started.elapsed()>=limit{if let Some(c)=child.take(){let _=c.kill();}cleanup_partial(&staged);return Err(format!("{name} helper timeout after {:.1}s (pid={pid})",limit.as_secs_f64()))}
    let ev=match tokio::time::timeout(Duration::from_millis(200),rx.recv()).await{Err(_)=>continue,Ok(Some(v))=>v,Ok(None)=>{if let Some(c)=child.take(){let _=c.kill();}cleanup_partial(&staged);return Err(format!("{name} закрыл канал без статуса завершения (pid={pid})"))}};
    match ev{CommandEvent::Stdout(b)=>stdout.extend_from_slice(&b),CommandEvent::Stderr(b)=>stderr.extend_from_slice(&b),CommandEvent::Error(e)=>{if let Some(c)=child.take(){let _=c.kill();}cleanup_partial(&staged);return Err(e)},CommandEvent::Terminated(t)=>{child.take();if t.code.unwrap_or(1)!=0{cleanup_partial(&staged);return Err(if stderr.is_empty(){format!("{name} завершился с кодом {:?}",t.code)}else{String::from_utf8_lossy(&stderr).trim().to_string()})}promote_partial(&staged)?;return Ok((stdout,stderr))},_=>{}}
  }
}'''
s=s[:start]+new+s[end:]

# A successful final mux is NOT deleted merely because metadata verification timed out.
old='''Err(e)=>{last_error=e;let _=std::fs::remove_dir_all(&work);let _=std::fs::remove_file(&out);if last_error==CANCELLED{return Err(last_error)}if last_error.starts_with("FINAL_VERIFY:"){return Err(last_error.trim_start_matches("FINAL_VERIFY: ").to_string())}if last_error.starts_with("FFMPEG_STALL:"){return Err(last_error.trim_start_matches("FFMPEG_STALL: ").to_string())}'''
new='''Err(e)=>{last_error=e;let _=std::fs::remove_dir_all(&work);if last_error==CANCELLED{let _=std::fs::remove_file(&out);return Err(last_error)}if last_error.starts_with("FINAL_VERIFY:"){let detail=last_error.trim_start_matches("FINAL_VERIFY: ").to_string();render_diag(job,"final-verify",&format!("FAILED file_preserved={} detail={}",out.display(),detail));return Err(format!("FINAL_VERIFY_FILE_PRESERVED: path={}; {}",out.display(),detail))}let _=std::fs::remove_file(&out);if last_error.starts_with("FFMPEG_STALL:"){return Err(last_error.trim_start_matches("FFMPEG_STALL: ").to_string())}'''
must(old in s,'render error ordering marker missing');s=s.replace(old,new,1)
must('FINAL_VERIFY_FILE_PRESERVED:' in s,'verification preservation marker missing')
p.write_text(s,encoding='utf-8')

p=need('src-tauri/src/queue.rs');q=p.read_text(encoding='utf-8')
needle='  if raw.contains("no_progress=")||raw.to_lowercase().contains("ffmpeg_stall"){return "FFmpeg остановлен watchdog: процесс перестал выдавать реальный прогресс. Partial-файл очищен; очередь продолжит следующий проект.".into()}\n'
must(needle in q,'8.46 watchdog friendly error missing')
if 'Видео создано, но не удалось завершить финальную проверку.' not in q:
 q=q.replace(needle,'  if raw.contains("FINAL_VERIFY_FILE_PRESERVED:"){return "Видео создано, но не удалось завершить финальную проверку. Готовый mux сохранён; подробности и путь записаны в диагностике.".into()}\n'+needle,1)
p.write_text(q,encoding='utf-8')
print('ENDLUME 8.46 post-hardening: helper partials + preserved mux on verify failure PASS')
