from pathlib import Path

p=Path('src-tauri/src/fast_render.rs')
s=p.read_text()

old_probe="""    let audio_mark=Instant::now();let mut durations=Vec::with_capacity(job.project.audio.len());for p in &job.project.audio{durations.push(duration(app,p).await?.max(0.001));}let target=job.settings.duration_hours*3600.0;let(final_duration,track_count)=final_whole_track_duration(target,&durations).ok_or(\"fast path cannot preserve whole-track duration semantics\")?;"""
new_probe="""    let audio_mark=Instant::now();let mut probes=Vec::with_capacity(job.project.audio.len());for p in &job.project.audio{let app=app.clone();let path=p.clone();probes.push(tauri::async_runtime::spawn(async move{duration(&app,&path).await}));}let mut durations=Vec::with_capacity(job.project.audio.len());for probe in probes{let d=probe.await.map_err(|e|format!(\"audio duration task failed: {e}\"))??;durations.push(d.max(0.001));}let target=job.settings.duration_hours*3600.0;let(final_duration,track_count)=final_whole_track_duration(target,&durations).ok_or(\"fast path cannot preserve whole-track duration semantics\")?;"""
if old_probe not in s: raise SystemExit('audio probe anchor mismatch')
s=s.replace(old_probe,new_probe,1)

old_vb="""async fn video_bitrate(app:&AppHandle,path:&Path)->Option<u64>{
  command(app,\"ffprobe\",vec![\"-v\",\"error\",\"-select_streams\",\"v:0\",\"-show_entries\",\"stream=bit_rate\",\"-of\",\"default=nw=1:nk=1\",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await.ok().and_then(|x|String::from_utf8_lossy(&x).trim().parse().ok())
}
"""
if old_vb not in s: raise SystemExit('video_bitrate anchor mismatch')
s=s.replace(old_vb,'',1)

old_verify="""async fn verify(app:&AppHandle,out:&Path,expected:f64,job:&QueueJob)->Result<(),String>{
  let d=duration(app,out.to_string_lossy().as_ref()).await?;
  if (d-expected).abs()>0.20{return Err(format!(\"fast path duration mismatch: {d:.3} vs {expected:.3}\"))}
  let raw=command(app,\"ffprobe\",vec![\"-v\",\"error\",\"-show_entries\",\"stream=codec_name,width,height,r_frame_rate,avg_frame_rate\",\"-of\",\"json\",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await?;
  let v:serde_json::Value=serde_json::from_slice(&raw).map_err(|e|e.to_string())?;let streams=v.get(\"streams\").and_then(|x|x.as_array()).ok_or(\"ffprobe streams missing\")?;let video=streams.iter().find(|s|s.get(\"width\").is_some()).ok_or(\"video stream missing\")?;
  streams.iter().find(|s|s.get(\"codec_name\").and_then(|x|x.as_str())==Some(\"mp3\")).ok_or(\"MP3 stream-copy missing\")?;
  if video.get(\"codec_name\").and_then(|x|x.as_str())!=Some(\"hevc\"){return Err(\"fast path output is not HEVC\".into())}
  if video.get(\"width\").and_then(|x|x.as_u64())!=Some(job.settings.width as u64)||video.get(\"height\").and_then(|x|x.as_u64())!=Some(job.settings.height as u64){return Err(\"fast path resolution mismatch\".into())}
  let fps=video.get(\"avg_frame_rate\").and_then(|x|x.as_str()).unwrap_or(\"\");let expected_fps=format!(\"{}/1\",job.settings.fps);if fps!=expected_fps{return Err(format!(\"fast path FPS mismatch: {fps} vs {expected_fps}\"))}Ok(())
}
"""
new_verify="""async fn verify(app:&AppHandle,out:&Path,expected:f64,job:&QueueJob)->Result<Option<u64>,String>{
  let raw=command(app,\"ffprobe\",vec![\"-v\",\"error\",\"-show_entries\",\"format=duration:stream=codec_name,width,height,r_frame_rate,avg_frame_rate,bit_rate\",\"-of\",\"json\",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await?;
  let v:serde_json::Value=serde_json::from_slice(&raw).map_err(|e|e.to_string())?;let d=v.get(\"format\").and_then(|x|x.get(\"duration\")).and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok()).ok_or(\"ffprobe duration missing\")?;if (d-expected).abs()>0.20{return Err(format!(\"fast path duration mismatch: {d:.3} vs {expected:.3}\"))}
  let streams=v.get(\"streams\").and_then(|x|x.as_array()).ok_or(\"ffprobe streams missing\")?;let video=streams.iter().find(|s|s.get(\"width\").is_some()).ok_or(\"video stream missing\")?;
  streams.iter().find(|s|s.get(\"codec_name\").and_then(|x|x.as_str())==Some(\"mp3\")).ok_or(\"MP3 stream-copy missing\")?;
  if video.get(\"codec_name\").and_then(|x|x.as_str())!=Some(\"hevc\"){return Err(\"fast path output is not HEVC\".into())}
  if video.get(\"width\").and_then(|x|x.as_u64())!=Some(job.settings.width as u64)||video.get(\"height\").and_then(|x|x.as_u64())!=Some(job.settings.height as u64){return Err(\"fast path resolution mismatch\".into())}
  let fps=video.get(\"avg_frame_rate\").and_then(|x|x.as_str()).unwrap_or(\"\");let expected_fps=format!(\"{}/1\",job.settings.fps);if fps!=expected_fps{return Err(format!(\"fast path FPS mismatch: {fps} vs {expected_fps}\"))}Ok(video.get(\"bit_rate\").and_then(|x|x.as_str()).and_then(|x|x.parse::<u64>().ok()))
}
"""
if old_verify not in s: raise SystemExit('verify anchor mismatch')
s=s.replace(old_verify,new_verify,1)

old_fin="""    let finalize_mark=Instant::now();verify(app,&out,final_duration,job).await?;write_side_files(job,&out,&durations,track_count)?;let bytes=fs::metadata(&out).ok().map(|m|m.len());let bitrate=video_bitrate(app,&out).await;let finalize_ms=finalize_mark.elapsed().as_secs_f64()*1000.0;"""
new_fin="""    let finalize_mark=Instant::now();let bitrate=verify(app,&out,final_duration,job).await?;write_side_files(job,&out,&durations,track_count)?;let bytes=fs::metadata(&out).ok().map(|m|m.len());let finalize_ms=finalize_mark.elapsed().as_secs_f64()*1000.0;"""
if old_fin not in s: raise SystemExit('finalize anchor mismatch')
s=s.replace(old_fin,new_fin,1)

p.write_text(s)
print('FAST_MARGIN_PATCH_APPLIED=1')
