#!/usr/bin/env python3
from pathlib import Path
import json,re

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'src-tauri/src/render.rs'
s=R.read_text()

def once(text,old,new,label):
    n=text.count(old)
    if n!=1: raise SystemExit(f'8.57 migration: {label}: expected 1 anchor, found {n}')
    return text.replace(old,new,1)

# Fix 1: cached keyed Effects must not terminate the Strict master timeline.
# This compositor-lifetime bug is separate from the VideoToolbox GOP bug.
old='graph.push_str(&format!(";[{idx}:v]fps={},format=argb[{fx}];[{base}][{fx}]overlay=x=\'{x}\':y=\'{y}\':shortest=1:eof_action=repeat:format=auto[{next}]",s.fps));base=next;continue'
new='graph.push_str(&format!(";[{idx}:v]fps={},setpts=PTS-STARTPTS,format=argb[{fx}];[{base}][{fx}]overlay=x=\'{x}\':y=\'{y}\':shortest=0:repeatlast=1:eof_action=repeat:format=auto[{next}]",s.fps));base=next;continue'
s=once(s,old,new,'strict-prealpha lifetime')

# Fix 2: physical Apple-Silicon VideoToolbox diagnostics proved that GOP 3381
# writes all 3381 HEVC packets but becomes undecodable after 2048 frames with
# RPS/POC errors. GOP 1800 and 1200 decode all 3381 frames/packets. Preserve
# the full master, q:v 100 and 60 FPS; cap only VideoToolbox keyframe interval.
old='fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}\n\nfn hybrid_fidelity_args(s:&RenderSettings,encoder:&str,duration:f64)->Vec<String>{'
new='fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}\n\nconst STRICT_857_MAX_GOP_FRAMES:u32=1800;\n\nfn hybrid_fidelity_args(s:&RenderSettings,encoder:&str,duration:f64)->Vec<String>{'
s=once(s,old,new,'named safe GOP constant')
old='let frames=(s.fps.max(1) as f64*duration.max(2.0)).round().max(1.0) as u32;\n  let g=frames.to_string();'
new='let frames=(s.fps.max(1) as f64*duration.max(2.0)).round().max(1.0) as u32;\n  let g=if encoder=="hevc_videotoolbox"{frames.min(STRICT_857_MAX_GOP_FRAMES)}else{frames}.to_string();'
s=once(s,old,new,'VideoToolbox-only safe GOP cap')

# Fix 3: packet-count integrity is required in addition to decoded-frame count.
frames_probe='''async fn probe_video_frames_852(app:&AppHandle,path:&Path)->Result<usize,String>{\n  let args=vec!["-v","error","-count_frames","-select_streams","v:0","-show_entries","stream=nb_read_frames","-of","default=nw=1:nk=1",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n  let (o,_)=output(app,"ffprobe",args).await?;String::from_utf8_lossy(&o).trim().parse::<usize>().map_err(|_|format!("Не удалось посчитать кадры: {}",path.display()))\n}\n'''
packets_probe=frames_probe+'''\nasync fn probe_video_packets_857(app:&AppHandle,path:&Path)->Result<usize,String>{\n  let args=vec!["-v","error","-count_packets","-select_streams","v:0","-show_entries","stream=nb_read_packets","-of","default=nw=1:nk=1",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n  let (o,_)=output(app,"ffprobe",args).await?;String::from_utf8_lossy(&o).trim().parse::<usize>().map_err(|_|format!("Не удалось посчитать video packets: {}",path.display()))\n}\n'''
s=once(s,frames_probe,packets_probe,'strict packet probe')

old='let vm=Instant::now();run_ffmpeg(app,job,started,timer,args,"Strict 8.56: fidelity master полного Effects-цикла",55.0,18.0,duration,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"strict-visual-master",vm.elapsed().as_secs_f64());let got=probe_video_frames_852(app,&master).await?;if got!=master_frames{return Err(format!("Strict 8.56 master: {got} кадров вместо {master_frames}"))}'
new='let vm=Instant::now();run_ffmpeg(app,job,started,timer,args,"Strict 8.57: fidelity master полного Effects-цикла",55.0,18.0,duration,encoder,attempt,cancel).await?;emit_timing(app,&job.project.id,"strict-visual-master",vm.elapsed().as_secs_f64());let got=probe_video_frames_852(app,&master).await?;let packets=probe_video_packets_857(app,&master).await?;if got!=master_frames||packets!=master_frames{return Err(format!("Strict 8.57 master integrity: frames={got}/{master_frames}, packets={packets}/{master_frames}"))}'
s=once(s,old,new,'strict master frame+packet integrity')

# Apply the same frame+packet invariant to the one-Subscribe periodic path and
# all stream-copied pieces before they are expanded into the final sample table.
old='let frames=probe_video_frames_852(app,&out).await?;if frames!=plan.master_frames{return Err(format!("8.52 master: {} кадров вместо {}",frames,plan.master_frames))}Ok(out)'
new='let frames=probe_video_frames_852(app,&out).await?;let packets=probe_video_packets_857(app,&out).await?;if frames!=plan.master_frames||packets!=plan.master_frames{return Err(format!("Strict 8.57 periodic master integrity: frames={frames}/{}, packets={packets}/{}",plan.master_frames,plan.master_frames))}Ok(out)'
s=once(s,old,new,'periodic master integrity')
old='let got=probe_video_frames_852(app,out).await?;if got!=frames{return Err(format!("8.52 slice: {got} кадров вместо {frames}"))}Ok(())'
new='let got=probe_video_frames_852(app,out).await?;let packets=probe_video_packets_857(app,out).await?;if got!=frames||packets!=frames{return Err(format!("Strict 8.57 slice integrity: frames={got}/{frames}, packets={packets}/{frames}"))}Ok(())'
s=once(s,old,new,'periodic slice integrity')
old='run_ffmpeg(app,job,started,timer,args,"8.52: добавляю Subscribe один раз на цикл",69.0,4.0,duration,encoder,attempt,cancel).await?;let got=probe_video_frames_852(app,&out).await?;if got!=frames{return Err(format!("8.52 Subscribe: {got} кадров вместо {frames}"))}Ok(out)'
new='run_ffmpeg(app,job,started,timer,args,"8.57: добавляю Subscribe один раз на цикл",69.0,4.0,duration,encoder,attempt,cancel).await?;let got=probe_video_frames_852(app,&out).await?;let packets=probe_video_packets_857(app,&out).await?;if got!=frames||packets!=frames{return Err(format!("Strict 8.57 Subscribe integrity: frames={got}/{frames}, packets={packets}/{frames}"))}Ok(out)'
s=once(s,old,new,'subscribe segment integrity')
old='run_ffmpeg(app,job,started,timer,args,"8.52: собираю один физический 300s video-cycle",74.0,3.0,expected_frames as f64/job.settings.fps.max(1) as f64,encoder,attempt,cancel).await?;let got=probe_video_frames_852(app,out).await?;if got!=expected_frames{return Err(format!("8.52 seed video: {got} кадров вместо {expected_frames}"))}Ok(())'
new='run_ffmpeg(app,job,started,timer,args,"8.57: собираю один физический video-cycle",74.0,3.0,expected_frames as f64/job.settings.fps.max(1) as f64,encoder,attempt,cancel).await?;let got=probe_video_frames_852(app,out).await?;let packets=probe_video_packets_857(app,out).await?;if got!=expected_frames||packets!=expected_frames{return Err(format!("Strict 8.57 seed integrity: frames={got}/{expected_frames}, packets={packets}/{expected_frames}"))}Ok(())'
s=once(s,old,new,'periodic seed integrity')

# Fix 4: the final Strict output used to verify only duration, audio presence,
# dimensions and FPS. Verify the actual delivery contract too: HEVC/yuv420p,
# original MP3 codec, 400-700 MB envelope, tight duration, and random-access
# decodability at beginning/middle/tail. This catches broken zero-copy sample
# tables and corrupt tails before render-done is emitted.
periodic_anchor='''\n\n#[derive(Clone)]\nstruct Periodic852Plan'''
strict_verify=r'''

async fn verify_strict_857_result(app:&AppHandle,out:&Path,expected:f64)->Result<(),String>{
  let bytes=std::fs::metadata(out).map_err(|e|format!("Strict 8.57 final stat: {e}"))?.len();
  if bytes<400_000_000||bytes>700_000_000{return Err(format!("Strict 8.57 final size: {} MB вне 400-700 MB",bytes/1_000_000))}
  let d=probe_duration(app,out.to_string_lossy().as_ref()).await?;
  if (d-expected).abs()>1.0{return Err(format!("Strict 8.57 final duration: {:.3} вместо {:.3}",d,expected))}
  let args=vec!["-v","error","-show_entries","stream=codec_type,codec_name,pix_fmt,width,height,avg_frame_rate,sample_rate,channels","-of","json",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  let (stdout,_)=output(app,"ffprobe",args).await?;let v:serde_json::Value=serde_json::from_slice(&stdout).map_err(|e|e.to_string())?;let streams=v.get("streams").and_then(|x|x.as_array()).ok_or("Strict 8.57: FFprobe streams отсутствуют")?;
  let video=streams.iter().find(|x|x.get("codec_type").and_then(|y|y.as_str())==Some("video")).ok_or("Strict 8.57: video stream отсутствует")?;
  let audio=streams.iter().find(|x|x.get("codec_type").and_then(|y|y.as_str())==Some("audio")).ok_or("Strict 8.57: audio stream отсутствует")?;
  if video.get("codec_name").and_then(|x|x.as_str())!=Some("hevc"){return Err("Strict 8.57: final video codec не HEVC".into())}
  if video.get("pix_fmt").and_then(|x|x.as_str())!=Some("yuv420p"){return Err("Strict 8.57: final pixel format не yuv420p".into())}
  if video.get("width").and_then(|x|x.as_u64())!=Some(1920)||video.get("height").and_then(|x|x.as_u64())!=Some(1080){return Err("Strict 8.57: final resolution не 1920x1080".into())}
  if video.get("avg_frame_rate").and_then(|x|x.as_str())!=Some("60/1"){return Err(format!("Strict 8.57: final FPS {:?}, ожидается 60/1",video.get("avg_frame_rate")))}
  if audio.get("codec_name").and_then(|x|x.as_str())!=Some("mp3"){return Err(format!("Strict 8.57: final audio codec {:?}, ожидается untouched MP3",audio.get("codec_name")))}
  for pos in [0.0,(expected*0.5).max(0.0),(expected-2.0).max(0.0)]{
    let ss=format!("{pos:.3}");let args=vec!["-v","error","-ss",ss.as_str(),"-i",out.to_string_lossy().as_ref(),"-map","0:v:0","-frames:v","2","-f","null","-"].into_iter().map(String::from).collect();
    output(app,"ffmpeg",args).await.map_err(|e|format!("Strict 8.57 video seek/decode @ {ss}s: {e}"))?;
  }
  for pos in [0.0,(expected-2.0).max(0.0)]{
    let ss=format!("{pos:.3}");let args=vec!["-v","error","-ss",ss.as_str(),"-i",out.to_string_lossy().as_ref(),"-map","0:a:0","-t","0.25","-f","null","-"].into_iter().map(String::from).collect();
    output(app,"ffmpeg",args).await.map_err(|e|format!("Strict 8.57 audio seek/decode @ {ss}s: {e}"))?;
  }
  Ok(())
}
'''
s=once(s,periodic_anchor,strict_verify+periodic_anchor,'strict final verifier')
old='emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&encoder,attempt,None);verify_result(app,&out,final_duration,&job.settings).await?;'
new='emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&encoder,attempt,None);verify_result(app,&out,final_duration,&job.settings).await?;if smart_repeat{verify_strict_857_result(app,&out,final_duration).await?;}'
s=once(s,old,new,'strict final verifier dispatch')

s=s.replace('Strict 8.56 zero-copy готов','Strict 8.57 zero-copy готов')
R.write_text(s)

# Version manifests.
for rel in ['package.json','src-tauri/tauri.conf.json']:
    p=ROOT/rel;d=json.loads(p.read_text());d['version']='1.0.0-alpha.8.57';p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'src-tauri/Cargo.toml';txt=p.read_text();txt,n=re.subn(r'(?m)^version\s*=\s*"1\.0\.0-alpha\.8\.56"$', 'version = "1.0.0-alpha.8.57"',txt,count=1)
if n!=1: raise SystemExit('8.57 migration: Cargo version anchor missing')
p.write_text(txt)
p=ROOT/'package-lock.json'
if p.exists():
    d=json.loads(p.read_text());d['version']='1.0.0-alpha.8.57'
    if isinstance(d.get('packages'),dict) and '' in d['packages']:d['packages']['']['version']='1.0.0-alpha.8.57'
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

# Keep visible Update Center in sync with the installed bundle.
P=ROOT/'src/pages/SettingsPage.tsx'
ui=P.read_text()
ui=once(ui,'ENDLUME Studio 1.0.0-alpha.8.41','ENDLUME Studio 1.0.0-alpha.8.57','settings visible version')
ui=once(ui,"update.current||'1.0.0-alpha.8.41'","update.current||'1.0.0-alpha.8.57'",'settings updater fallback')
ui=once(ui,'Версия <b>1.0.0-alpha.8.41</b>','Версия <b>1.0.0-alpha.8.57</b>','about visible version')
ui=once(ui,'Обновлено <b>31.08.2026</b>','Обновлено <b>06.09.2026</b>','about visible date')
P.write_text(ui)

H=ROOT/'src/components/ReleaseHistory.tsx'
h=H.read_text()
anchor="const releases:Release[]=[\n  {version:'1.0.0-alpha.8.41',date:'31.08.2026',current:true,title:'60 FPS • Stability • Gapless Audio • Chroma',items:["
insert="""const releases:Release[]=[
  {version:'1.0.0-alpha.8.57',date:'06.09.2026',current:true,title:'Strict Master Integrity • Safe VideoToolbox GOP',items:[
    'Исправлена отдельная ошибка lifetime keyed Effects: короткий cached Effect больше не завершает Strict master раньше базового таймлайна.',
    'Физическая диагностика Apple Silicon выявила отдельный HEVC VideoToolbox дефект длинного GOP: GOP 3381 записывал 3381 packets, но декодировались только 2048 frames с RPS/POC errors.',
    'Для HEVC VideoToolbox keyframe interval ограничен 1800 кадрами; полный master остаётся 3381 кадров, 1920×1080/60 FPS и q:v 100.',
    'Strict runtime проверяет decoded frames и encoded packets для master, Subscribe-сегментов и seed до zero-copy expansion.',
    'Перед render-done итог дополнительно проверяется: HEVC/yuv420p, 1920×1080/60, untouched MP3, 400–700 МБ, точная длительность и seek/decode в начале, середине и хвосте.',
    'Экран Обновления и О программе синхронизирован с текущей версией 8.57; VYRON bridge и updater identity сохранены.'
  ]},
  {version:'1.0.0-alpha.8.56',date:'05.09.2026',current:false,title:'Render Isolation • Strict Output Contract',items:[
    'Strict one-image render изолирован от software fallback и случайных legacy-путей.',
    'Whole-track audio и нулевой crossfade закреплены для производственного VYRON-пайплайна.',
    'Финальный файл проходит строгий контракт размера 400–700 МБ и проверку результата до публикации.'
  ]},
  {version:'1.0.0-alpha.8.41',date:'31.08.2026',current:false,title:'60 FPS • Stability • Gapless Audio • Chroma',items:["""
h=once(h,anchor,insert,'release history current version')
H.write_text(h)

print('PASS: ENDLUME 8.57 Effects lifetime + safe VideoToolbox GOP + frame/packet/seek final integrity hotfix applied')
