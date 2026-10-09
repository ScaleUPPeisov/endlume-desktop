from pathlib import Path

p=Path('src-tauri/src/render.rs')
s=p.read_text()

if 'fn exact_segment_frames(' in s and "shortest=0:eof_action=repeat" in s:
    print('LEGACY_DTS_V3_ALREADY_PRESENT=1')
    raise SystemExit(0)

anchor='''fn timed_effects(effects:&[EffectPreset],final_duration:f64)->bool{effects.iter().any(|e|e.enabled&&(e.start_sec>0.01||e.end_sec.map(|x|x<final_duration-0.01).unwrap_or(false)))}\n'''
helper='''fn timed_effects(effects:&[EffectPreset],final_duration:f64)->bool{effects.iter().any(|e|e.enabled&&(e.start_sec>0.01||e.end_sec.map(|x|x<final_duration-0.01).unwrap_or(false)))}\nfn exact_segment_frames(len:f64,fps:u32)->u64{(len.max(0.0)*fps.max(1) as f64).round().max(1.0) as u64}\n'''
if 'fn exact_segment_frames(' not in s:
    if s.count(anchor)!=1: raise SystemExit('timed_effects anchor mismatch')
    s=s.replace(anchor,helper)

old_copy='''async fn copy_segment(app:&AppHandle,job:&QueueJob,variant:&Path,variant_duration:f64,start:f64,len:f64,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,base:f64,span:f64,started:i64,timer:&Instant)->Result<(),String>{\n  let phase=(start%variant_duration.max(0.1)).max(0.0);let args=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&phase.to_string(),"-i",variant.to_string_lossy().as_ref(),"-t",&len.to_string(),"-an","-c:v","copy","-avoid_negative_ts","make_zero","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();run_ffmpeg(app,job,started,timer,args,"Собираю визуальные сегменты",base,span,len,encoder,attempt,cancel).await\n}\n'''
new_copy='''async fn copy_segment(app:&AppHandle,job:&QueueJob,variant:&Path,variant_duration:f64,start:f64,len:f64,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,base:f64,span:f64,started:i64,timer:&Instant)->Result<(),String>{\n  let phase=(start%variant_duration.max(0.1)).max(0.0);let fps=job.settings.fps.max(1);let frames=exact_segment_frames(len,fps);let vf=format!("fps={fps},trim=end_frame={frames},setpts=N/({fps}*TB),format=yuv420p");let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&phase.to_string(),"-i",variant.to_string_lossy().as_ref(),"-vf",&vf,"-frames:v",&frames.to_string(),"-an"].into_iter().map(String::from).collect();args.extend(encoder_args(encoder,&job.settings,false));args.extend(vec!["-r",&fps.to_string(),"-fps_mode","cfr","-video_track_timescale","60000","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));run_ffmpeg(app,job,started,timer,args,"Собираю визуальные сегменты",base,span,len,encoder,attempt,cancel).await\n}\n'''
if old_copy in s:
    s=s.replace(old_copy,new_copy)
elif new_copy not in s:
    raise SystemExit('copy_segment anchor mismatch')

old_sub='''async fn render_sub_segment(app:&AppHandle,job:&QueueJob,variant:&Path,variant_duration:f64,start:f64,len:f64,active:&[SubEvent],out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,base:f64,span:f64,started:i64,timer:&Instant)->Result<(),String>{\n  let phase=(start%variant_duration.max(0.1)).max(0.0);let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&phase.to_string(),"-i",variant.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n  for ev in active{let offset=(start-ev.event_start).max(0.0);args.extend(vec!["-ss",&offset.to_string(),"-i",ev.sub.effect.source.as_str()].into_iter().map(String::from));}\n  let sub_effects=active.iter().map(|e|e.sub.effect.clone()).collect::<Vec<_>>();let (graph,last)=apply_effects_filter("[0:v]setpts=PTS-STARTPTS[b0]".into(),"b0".into(),&sub_effects,&job.settings,1);let graph=format!("{graph};[{last}]format=yuv420p[outv]");\n  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t",&len.to_string(),"-an"].into_iter().map(String::from));args.extend(encoder_args(encoder,&job.settings,false));args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));run_ffmpeg(app,job,started,timer,args,"Добавляю Subscribe",base,span,len,encoder,attempt,cancel).await\n}\n'''
new_sub='''async fn render_sub_segment(app:&AppHandle,job:&QueueJob,variant:&Path,variant_duration:f64,start:f64,len:f64,active:&[SubEvent],out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,base:f64,span:f64,started:i64,timer:&Instant)->Result<(),String>{\n  let phase=(start%variant_duration.max(0.1)).max(0.0);let fps=job.settings.fps.max(1);let frames=exact_segment_frames(len,fps);let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&phase.to_string(),"-i",variant.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n  for ev in active{let offset=(start-ev.event_start).max(0.0);args.extend(vec!["-ss",&offset.to_string(),"-i",ev.sub.effect.source.as_str()].into_iter().map(String::from));}\n  let sub_effects=active.iter().map(|e|e.sub.effect.clone()).collect::<Vec<_>>();let (graph,last)=apply_effects_filter("[0:v]setpts=PTS-STARTPTS[b0]".into(),"b0".into(),&sub_effects,&job.settings,1);let graph=format!("{graph};[{last}]fps={fps},trim=end_frame={frames},setpts=N/({fps}*TB),format=yuv420p[outv]");\n  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-frames:v",&frames.to_string(),"-an"].into_iter().map(String::from));args.extend(encoder_args(encoder,&job.settings,false));args.extend(vec!["-r",&fps.to_string(),"-fps_mode","cfr","-video_track_timescale","60000","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));run_ffmpeg(app,job,started,timer,args,"Добавляю Subscribe",base,span,len,encoder,attempt,cancel).await\n}\n'''
if old_sub in s:
    s=s.replace(old_sub,new_sub)
elif new_sub not in s:
    raise SystemExit('render_sub_segment anchor mismatch')

old_overlay="overlay=x='{x}':y='{y}':shortest=1:eof_action=repeat"
new_overlay="overlay=x='{x}':y='{y}':shortest=0:eof_action=repeat"
if old_overlay in s:
    if s.count(old_overlay)!=1: raise SystemExit('overlay anchor count mismatch')
    s=s.replace(old_overlay,new_overlay)
elif new_overlay not in s:
    raise SystemExit('overlay anchor missing')

p.write_text(s)
print('LEGACY_DTS_V3_APPLIED=1')
