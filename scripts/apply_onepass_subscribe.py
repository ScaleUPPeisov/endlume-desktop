from pathlib import Path

p = Path('src-tauri/src/fast_render.rs')
s = p.read_text()

MARKER = 'async fn encode_subscribe_mux_audio('
if MARKER in s:
    print('ONEPASS_PATCH_ALREADY_PRESENT=1')
    raise SystemExit(0)

anchor = '''async fn encode_master(app:&AppHandle,job:&QueueJob,plan:&FastVisualPlan,master:&Path)->Result<(),String>{if plan.subscribe.is_some(){encode_subscribe_master(app,job,plan,master).await}else{encode_cycle_master(app,job,plan,master).await}}\n'''
if s.count(anchor) != 1:
    raise SystemExit('encode_master anchor mismatch')

fn = r'''async fn encode_subscribe_mux_audio(app:&AppHandle,job:&QueueJob,plan:&FastVisualPlan,list:&Path,out:&Path)->Result<(),String>{
  let sub=plan.subscribe.as_ref().ok_or("Subscribe plan missing")?;let fps=job.settings.fps.to_string();
  let mut args=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",fps.as_str(),"-i",job.project.media[0].as_str(),"-stream_loop","-1","-i",sub.effect.source.as_str(),"-f","concat","-safe","0","-i",list.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();
  let graph=format!("{}[base];[base]split=2[stillbase][subbase]",visual_spec::base_filter("0:v",job.settings.width,job.settings.height,job.settings.fps));let one=vec![sub.effect.clone()];let (mut graph,last)=visual_spec::apply_effects_filter(graph,"subbase".into(),&one,job.settings.width,job.settings.height,job.settings.fps,1);
  graph.push_str(&format!(";[stillbase]trim=end_frame=1,setpts=PTS-STARTPTS[still];[{last}]trim=end_frame={},setpts=PTS-STARTPTS[subseg];[still][subseg]concat=n=2:v=1:a=0,format=yuv420p[outv]",plan.subscribe_frames));
  args.extend(vec!["-filter_complex",graph.as_str(),"-map","[outv]","-map","2:a:0","-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-q:v","75","-b:v","8M","-maxrate","20M","-bufsize","80M","-g","1","-tag:v","hvc1","-fps_mode","cfr","-r",fps.as_str(),"-c:a","copy","-video_track_timescale","60000","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));command(app,"ffmpeg",args).await.map(|_|())
}
'''
s = s.replace(anchor, fn + anchor)

old = r'''    cancelled(cancel)?;let t=Instant::now();encode_master(app,job,plan,&master).await?;let master_ms=t.elapsed().as_secs_f64()*1000.0;let _=app.emit("engine-timing",json!({"id":job.project.id,"key":"fast-master-render-ms","milliseconds":master_ms}));
    cancelled(cancel)?;let t=Instant::now();command(app,"ffmpeg",vec!["-hide_banner","-loglevel","error","-i",master.to_string_lossy().as_ref(),"-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-video_track_timescale","60000","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await?;let mux_ms=t.elapsed().as_secs_f64()*1000.0;let _=app.emit("engine-timing",json!({"id":job.project.id,"key":"fast-mux-ms","milliseconds":mux_ms}));
'''
new = r'''    cancelled(cancel)?;let(master_ms,mux_ms,encode_mux_ms)=if plan.subscribe.is_some(){let t=Instant::now();encode_subscribe_mux_audio(app,job,plan,&list,&out).await?;let combined=t.elapsed().as_secs_f64()*1000.0;let _=app.emit("engine-timing",json!({"id":job.project.id,"key":"fast-encode-mux-ms","milliseconds":combined}));(0.0,0.0,Some(combined))}else{let t=Instant::now();encode_master(app,job,plan,&master).await?;let master_ms=t.elapsed().as_secs_f64()*1000.0;let _=app.emit("engine-timing",json!({"id":job.project.id,"key":"fast-master-render-ms","milliseconds":master_ms}));cancelled(cancel)?;let t=Instant::now();command(app,"ffmpeg",vec!["-hide_banner","-loglevel","error","-i",master.to_string_lossy().as_ref(),"-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-video_track_timescale","60000","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await?;let mux_ms=t.elapsed().as_secs_f64()*1000.0;let _=app.emit("engine-timing",json!({"id":job.project.id,"key":"fast-mux-ms","milliseconds":mux_ms}));(master_ms,mux_ms,None)};
'''
if s.count(old) != 1:
    raise SystemExit('run_fast serial block mismatch')
s = s.replace(old, new)

old_event = '"masterMs":master_ms,"muxMs":mux_ms,"timelineMs":timeline_ms'
new_event = '"masterMs":master_ms,"muxMs":mux_ms,"encodeMuxMs":encode_mux_ms,"timelineMs":timeline_ms'
if s.count(old_event) != 1:
    raise SystemExit('metrics anchor mismatch')
s = s.replace(old_event, new_event)

p.write_text(s)
print('ONEPASS_PATCH_APPLIED=1')
