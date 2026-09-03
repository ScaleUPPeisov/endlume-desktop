#!/usr/bin/env python3
from pathlib import Path
import re

VERSION='1.0.0-alpha.8.45'
ROOT=Path(__file__).resolve().parent.parent


def need(rel):
    p=ROOT/rel
    if not p.is_file():
        raise SystemExit(f'8.45: missing {rel}')
    return p


def must(cond,msg):
    if not cond:
        raise SystemExit('8.45: '+msg)

# 8.45 is intentionally a FINALIZE-ONLY hotfix on top of the proven 8.44 tree.
# It does not alter media preparation, codecs, bitrate/quality, audio, Effects,
# Subscribe, VYRON bridge, updater identity or UI motion.
p=need('src-tauri/src/render.rs')
r=p.read_text(encoding='utf-8')

# Prove the exact regression exists before touching it: 8.43 added a full-file
# packet count to final FFprobe. A 2h CFR60 file can contain >400k packets, so
# this makes the 97% phase scan the whole output even though muxing has finished.
must('"-count_packets"' in r,'8.43 full-file packet scan marker missing')
must('nb_read_packets' in r,'8.43 packet-count verification marker missing')
must('Финальная проверка FFprobe' in r,'final verification stage missing')
must('"-c:v","copy","-c:a","copy","-video_track_timescale","60000"' in r,'8.43 stream-copy final mux changed')

start=r.find('async fn verify_result(')
end=r.find('\n\npub async fn render_job',start)
must(start>=0 and end>start,'verify_result block missing')

new_verify=r'''#[derive(Debug,Clone)]
struct FinalProbe{video_bitrate:Option<u64>}

fn final_verify_error(msg:impl Into<String>)->String{format!("FINAL_VERIFY: {}",msg.into())}

async fn ffprobe_output_timeout(app:&AppHandle,args:Vec<String>,timeout:Duration)->Result<(Vec<u8>,Vec<u8>),String>{
  let (mut rx,child)=app.shell().sidecar("ffprobe").map_err(|e|e.to_string())?.args(args).spawn().map_err(|e|e.to_string())?;
  let mut child=Some(child);let started=Instant::now();let mut stdout=Vec::new();let mut stderr=Vec::new();
  loop{
    if started.elapsed()>=timeout{
      if let Some(c)=child.take(){let _=c.kill();}
      return Err(format!("FFprobe timeout after {:.1}s",timeout.as_secs_f64()))
    }
    let left=timeout.saturating_sub(started.elapsed());let slice=left.min(Duration::from_millis(200));
    let event=tokio::time::timeout(slice,rx.recv()).await;
    let ev=match event{Err(_)=>continue,Ok(Some(ev))=>ev,Ok(None)=>return Err("FFprobe закрыл канал без статуса завершения".into())};
    match ev{
      CommandEvent::Stdout(bytes)=>stdout.extend_from_slice(&bytes),
      CommandEvent::Stderr(bytes)=>stderr.extend_from_slice(&bytes),
      CommandEvent::Error(e)=>{if let Some(c)=child.take(){let _=c.kill();}return Err(e)},
      CommandEvent::Terminated(t)=>{
        child.take();
        if t.code.unwrap_or(1)!=0{return Err(if stderr.is_empty(){format!("FFprobe завершился с кодом {:?}",t.code)}else{String::from_utf8_lossy(&stderr).trim().to_string()})}
        return Ok((stdout,stderr))
      },
      _=>{}
    }
  }
}

fn json_num(v:Option<&serde_json::Value>)->Option<f64>{
  match v{
    Some(serde_json::Value::Number(n))=>n.as_f64(),
    Some(serde_json::Value::String(s))=>s.parse::<f64>().ok(),
    _=>None,
  }
}
fn json_u64(v:Option<&serde_json::Value>)->Option<u64>{
  match v{
    Some(serde_json::Value::Number(n))=>n.as_u64(),
    Some(serde_json::Value::String(s))=>s.parse::<u64>().ok(),
    _=>None,
  }
}
fn parse_rate(rate:&str)->f64{
  let mut it=rate.split('/');let n=it.next().and_then(|x|x.parse::<f64>().ok()).unwrap_or(0.0);let d=it.next().and_then(|x|x.parse::<f64>().ok()).unwrap_or(1.0).max(0.000001);n/d
}

async fn verify_result_once(app:&AppHandle,out:&Path,expected:f64,s:&RenderSettings)->Result<FinalProbe,String>{
  // IMPORTANT: no -count_packets here. Container/stream metadata is enough for
  // final integrity and CFR metadata validation; scanning every packet is not.
  let args=vec![
    "-v","error",
    "-show_entries","format=duration:stream=codec_type,width,height,r_frame_rate,avg_frame_rate,nb_frames,duration,bit_rate",
    "-of","json",
    out.to_string_lossy().as_ref()
  ].into_iter().map(String::from).collect();
  let (stdout,_)=ffprobe_output_timeout(app,args,Duration::from_secs(12)).await?;
  let v:serde_json::Value=serde_json::from_slice(&stdout).map_err(|e|format!("FFprobe JSON: {e}"))?;
  let d=json_num(v.get("format").and_then(|x|x.get("duration"))).ok_or("FFprobe не вернул длительность")?;
  if (d-expected).abs()>4.0{return Err(format!("Финальный файл имеет неверную длительность: {:.1} сек вместо {:.1}",d,expected))}
  let streams=v.get("streams").and_then(|x|x.as_array()).ok_or("FFprobe не вернул streams")?;
  let video=streams.iter().find(|x|x.get("codec_type").and_then(|x|x.as_str())==Some("video")).ok_or("FFprobe не вернул видеопоток")?;
  let audio=streams.iter().find(|x|x.get("codec_type").and_then(|x|x.as_str())==Some("audio")).ok_or("В финальном файле отсутствует аудиодорожка")?;
  let w=video.get("width").and_then(|x|x.as_u64()).unwrap_or(0) as u32;let h=video.get("height").and_then(|x|x.as_u64()).unwrap_or(0) as u32;
  if w!=s.width||h!=s.height{return Err(format!("Неверное разрешение результата: {}x{} вместо {}x{}",w,h,s.width,s.height))}
  let r_fps=parse_rate(video.get("r_frame_rate").and_then(|x|x.as_str()).unwrap_or("0/1"));
  let a_fps=parse_rate(video.get("avg_frame_rate").and_then(|x|x.as_str()).unwrap_or("0/1"));
  let wanted=if s.fps>=50{60.0}else{30.0};
  if (r_fps-wanted).abs()>0.10||(a_fps-wanted).abs()>0.10||(r_fps-a_fps).abs()>0.10{return Err(format!("Ошибка FPS: запрошено {:.0}, r_frame_rate={:.3}, avg_frame_rate={:.3}",wanted,r_fps,a_fps))}
  // nb_frames is used only when the container already exposes it. We never ask
  // FFprobe to count packets across the two-hour file.
  if let (Some(frames),Some(stream_d))=(json_num(video.get("nb_frames")),json_num(video.get("duration"))){
    if frames>0.0&&stream_d>0.5{let measured=frames/stream_d;if (measured-wanted).abs()>0.30{return Err(format!("Ошибка FPS metadata: {:.3} вместо {:.0}",measured,wanted))}}
  }
  if let Some(ad)=json_num(audio.get("duration")){if ad>0.0&&(ad-d).abs()>4.5{return Err(format!("Длительность аудио отличается от контейнера: {:.1} сек vs {:.1}",ad,d))}}
  Ok(FinalProbe{video_bitrate:json_u64(video.get("bit_rate"))})
}

async fn verify_result(app:&AppHandle,out:&Path,expected:f64,s:&RenderSettings)->Result<FinalProbe,String>{
  let mut last=String::new();
  for attempt in 1..=2{
    match verify_result_once(app,out,expected,s).await{Ok(v)=>return Ok(v),Err(e)=>{last=e;if attempt<2{tokio::time::sleep(Duration::from_millis(250)).await;}}}
  }
  Err(final_verify_error(last))
}'''
r=r[:start]+new_verify+r[end:]

# Wire one verified metadata result through completion. Remove the second
# post-verification bitrate FFprobe entirely so telemetry can never hold 97%.
old='let result:Result<(Vec<f64>,f64),String>=async{'
must(old in r,'render result type marker missing')
r=r.replace(old,'let result:Result<(Vec<f64>,f64,Option<u64>),String>=async{',1)
old='emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&encoder,attempt,None);verify_result(app,&out,final_duration,&job.settings).await?;let result_stem=out.file_stem().and_then(|x|x.to_str()).unwrap_or(&job.project.name);write_side_files(job,&out_dir,&durations,final_duration,result_stem)?;Ok((durations,final_duration))'
must(old in r,'8.44 final verify sequence changed unexpectedly')
new='let verify_mark=Instant::now();emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&encoder,attempt,None);let final_probe=verify_result(app,&out,final_duration,&job.settings).await?;emit_timing(app,&job.project.id,"final-verify",verify_mark.elapsed().as_secs_f64());emit_progress(app,job,started,&timer,99.0,"Финализация результата",&encoder,attempt,None);let finalize_mark=Instant::now();let result_stem=out.file_stem().and_then(|x|x.to_str()).unwrap_or(&job.project.name);write_side_files(job,&out_dir,&durations,final_duration,result_stem)?;emit_timing(app,&job.project.id,"finalize",finalize_mark.elapsed().as_secs_f64());Ok((durations,final_duration,final_probe.video_bitrate))'
r=r.replace(old,new,1)
old='Ok((_durations,_fd))=>{let bytes=std::fs::metadata(&out).ok().map(|m|m.len());let bitrate=probe_video_bitrate(app,&out).await;'
must(old in r,'post-verify bitrate probe marker missing')
r=r.replace(old,'Ok((_durations,_fd,bitrate))=>{let bytes=std::fs::metadata(&out).ok().map(|m|m.len());',1)

# A final verification problem is not an encoder problem. Never throw away a
# completed 2h output and launch the automatic libx265 fallback because FFprobe
# timed out or metadata verification failed. Retry the probe locally above;
# after that surface a precise error and keep the existing encoder fallback only
# for actual render/encode failures.
old='if last_error==CANCELLED{return Err(last_error)}if attempt<2{emit_progress(app,job,started,&timer,2.0,"Проверка не пройдена — автоматический повтор",&encoder,attempt+1,None);}'
must(old in r,'render retry marker missing')
new='if last_error==CANCELLED{return Err(last_error)}if last_error.starts_with("FINAL_VERIFY:"){return Err(last_error.trim_start_matches("FINAL_VERIFY: ").to_string())}if attempt<2{emit_progress(app,job,started,&timer,2.0,"Ошибка рендера — резервный движок",&encoder,attempt+1,None);}'
r=r.replace(old,new,1)

# Hard guards: no quality/performance profile modifications in this hotfix.
must('"-count_packets"' not in r,'full-file packet scan survived')
must('nb_read_packets' not in r,'full-file packet counter survived')
must('ffprobe_output_timeout' in r and 'Duration::from_secs(12)' in r,'bounded FFprobe missing')
must('final-verify' in r and 'finalize' in r,'final timing telemetry missing')
must('let bitrate=probe_video_bitrate(app,&out).await;' not in r,'blocking post-verify bitrate probe survived')
for marker in [
    'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};',
    'fn cfr_output_args(',
    '"-fps_mode".into(),"cfr".into()',
    '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    'force_original_aspect_ratio=increase',
    'materialize_continuous_audio',
    'acrossfade=d={cf}:c1=tri:c2=tri',
]:
    must(marker in r,'protected 8.44 render invariant missing: '+marker)
p.write_text(r,encoding='utf-8')

# Version identity only. Do not modify Tauri identifier/updater endpoints.
for rel in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=need(rel);s=p.read_text(encoding='utf-8');s=re.sub(r'1\.0\.0-alpha\.8\.\d+',VERSION,s);p.write_text(s,encoding='utf-8')

# Release history entry; no navigation/design changes.
p=need('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.45',date:'03.09.2026',current:true,title:'Fast Finalize Hotfix',items:[
    'Исправлено зависание 97%: финальный FFprobe больше не перечитывает сотни тысяч пакетов двухчасового видео.',
    'Финальная проверка использует быстрые metadata-поля с жёстким timeout и одним локальным retry; завершение больше не блокируется отдельным bitrate probe.',
    'Ошибка FFprobe больше не запускает повторный двухчасовой рендер на libx265: резервный encoder остаётся только для реальной ошибки рендера.',
    'Видео/аудио/Effects/Subscribe, выбранные 30/60 FPS, 500k video budget, VYRON bridge и signed updater не изменены.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.45'" not in h:
    must(marker in h,'release history anchor missing');h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')

print('ENDLUME 8.45 fast bounded final verification hotfix: PASS')
