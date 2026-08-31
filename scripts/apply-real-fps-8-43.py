from pathlib import Path
import re


def must(cond,msg):
    if not cond:
        raise SystemExit('8.43: '+msg)

# FPS-only release. Do not touch bitrate, render architecture, audio, Effects UI or updater.
p=Path('src-tauri/src/render.rs')
r=p.read_text(encoding='utf-8')

# 8.41 hard-forced every Smart/Fidelity job to 60. Preserve the user's real 30/60 mode.
if 'resolved_job.settings.fps=60;' in r:
    r=r.replace(
        'resolved_job.settings.fps=60;',
        'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};',
        1,
    )
must('resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};' in r,
     '30/60 runtime normalization missing')
must('resolved_job.settings.fps=resolved_job.settings.fps.min(30);' not in r,
     'historical 60->30 clamp survived')

# Every actual video ENCODE must be CFR. The final long file is still stream-copy,
# preserving the proven fast short-master architecture.
if 'fn cfr_output_args(' not in r:
    marker='fn base_filter(s:&RenderSettings,label:&str)->String{'
    must(marker in r,'base_filter marker missing')
    helper='''fn cfr_output_args(s:&RenderSettings)->Vec<String>{\n  let fps=if s.fps>=50{60}else{30};\n  vec!["-fps_mode".into(),"cfr".into(),"-r".into(),fps.to_string(),"-video_track_timescale".into(),"60000".into()]\n}\n\n'''
    r=r.replace(marker,helper+marker,1)

# Smart still master(s).
r=r.replace(
    'args.extend(static_smart_encoder_args(s));\n  args.extend(vec!["-progress"',
    'args.extend(static_smart_encoder_args(s));\n  args.extend(cfr_output_args(s));\n  args.extend(vec!["-progress"',
    1,
)
# Inline image/non-image source clip encode.
r=r.replace(
    'if is_image(media){args.extend(static_smart_encoder_args(s));}else{args.extend(encoder_args(encoder,s,false));}args.extend(vec!["-progress"',
    'if is_image(media){args.extend(static_smart_encoder_args(s));}else{args.extend(encoder_args(encoder,s,false));}args.extend(cfr_output_args(s));args.extend(vec!["-progress"',
    1,
)
# Effects / Subscribe encoded variants. Replace every exact effective pattern.
r=r.replace(
    'args.extend(encoder_args(encoder,&job.settings,false));args.extend(vec!["-progress"',
    'args.extend(encoder_args(encoder,&job.settings,false));args.extend(cfr_output_args(&job.settings));args.extend(vec!["-progress"',
)

must('fn cfr_output_args(' in r,'CFR helper missing')
must(r.count('cfr_output_args(')>=4,'not all encoded video stages are CFR guarded')
must('fps={},setsar=1' in r,'base filter no longer derives FPS from RenderSettings')

# Final stream-copy mux must use a stable 60k video track timescale. This does NOT
# re-encode the two-hour file and therefore does not alter the speed/size budget.
final_mux_old='"-c:v","copy","-c:a","copy","-progress","pipe:1"'
final_mux_new='"-c:v","copy","-c:a","copy","-video_track_timescale","60000","-progress","pipe:1"'
if final_mux_old in r:
    r=r.replace(final_mux_old,final_mux_new,1)
must(final_mux_new in r,'final stream-copy mux timescale guard missing')

# Replace the old avg_frame_rate-only check with a final-file CFR contract.
start=r.find('async fn verify_result(')
end=r.find('\n\npub async fn render_job',start)
must(start>=0 and end>start,'verify_result helper missing')
new_verify=r'''async fn verify_result(app:&AppHandle,out:&Path,expected:f64,s:&RenderSettings)->Result<(),String>{
  let d=probe_duration(app,out.to_string_lossy().as_ref()).await?;
  if (d-expected).abs()>4.0{return Err(format!("Финальный файл имеет неверную длительность: {:0.1} сек вместо {:0.1}",d,expected))}
  if !probe_has_audio(app,out).await{return Err("В финальном файле отсутствует аудиодорожка".into())}
  if !probe_audio_decodes(app,out).await{return Err("Аудиодорожка есть, но не воспроизводится/не декодируется".into())}

  let args=vec![
    "-v","error","-select_streams","v:0","-count_packets",
    "-show_entries","stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_packets,duration",
    "-of","json",out.to_string_lossy().as_ref()
  ].into_iter().map(String::from).collect();
  let (stdout,_)=output(app,"ffprobe",args).await?;
  let v:serde_json::Value=serde_json::from_slice(&stdout).map_err(|e|e.to_string())?;
  let stream=v.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()).ok_or("FFprobe не вернул видеопоток")?;
  let w=stream.get("width").and_then(|x|x.as_u64()).unwrap_or(0) as u32;
  let h=stream.get("height").and_then(|x|x.as_u64()).unwrap_or(0) as u32;
  if w!=s.width||h!=s.height{return Err(format!("Неверное разрешение результата: {}x{} вместо {}x{}",w,h,s.width,s.height))}

  let parse_rate=|rate:&str|->f64{
    let mut it=rate.split('/');
    let n=it.next().and_then(|x|x.parse::<f64>().ok()).unwrap_or(0.0);
    let den=it.next().and_then(|x|x.parse::<f64>().ok()).unwrap_or(1.0).max(0.000001);
    n/den
  };
  let r_rate=stream.get("r_frame_rate").and_then(|x|x.as_str()).unwrap_or("0/1");
  let a_rate=stream.get("avg_frame_rate").and_then(|x|x.as_str()).unwrap_or("0/1");
  let r_fps=parse_rate(r_rate);
  let a_fps=parse_rate(a_rate);
  let wanted=if s.fps>=50{60.0}else{30.0};
  if (r_fps-wanted).abs()>0.10 || (a_fps-wanted).abs()>0.10 || (r_fps-a_fps).abs()>0.10{
    return Err(format!("Ошибка FPS: запрошено {:.0} FPS, финальный файл имеет r_frame_rate={:.3}, avg_frame_rate={:.3}",wanted,r_fps,a_fps))
  }

  let stream_d=stream.get("duration").and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok()).unwrap_or(d).max(0.001);
  let frames=stream.get("nb_frames").and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok())
    .or_else(||stream.get("nb_read_packets").and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok()));
  if let Some(frames)=frames{
    let measured=frames/stream_d;
    if (measured-wanted).abs()>0.20{
      return Err(format!("Ошибка FPS: запрошено {:.0} FPS, по числу кадров/пакетов финальный файл имеет {:.3} FPS",wanted,measured))
    }
  }
  Ok(())
}'''
r=r[:start]+new_verify+r[end:]

# Protect the accepted render contract.
must('fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' in r,'500k video budget changed')
must('"-maxrate","500k","-bufsize","4M"' in r,'x265 size guard changed')
must('"-b:v","500k","-maxrate","4M","-bufsize","16M"' in r,'VideoToolbox size guard changed')
must('force_original_aspect_ratio=increase' in r and 'crop={}:{}:(iw-ow)/2:(ih-oh)/2' in r,'1920x1080 cover/crop changed')
must('acrossfade=d={cf}:c1=tri:c2=tri' in r,'audio crossfade changed')
must('materialize_continuous_audio' in r,'gapless audio changed')
p.write_text(r,encoding='utf-8')

# Effects cache: keep 8.41 motion interpolation, and make the encoded cache CFR too.
p=Path('src-tauri/src/cache.rs')
c=p.read_text(encoding='utf-8')
must('minterpolate=fps={fps}:mi_mode=mci' in c,'8.41 Effects motion interpolation missing')
if '"-fps_mode","cfr","-r",fps_s.as_str()' not in c:
    old='''    let pix=if e.mode=="screen"{"rgb24"}else{"argb"};\n    let args=vec!["-hide_banner","-loglevel","error","-i",e.source.as_str(),"-vf",vf.as_str(),"-an","-c:v","qtrle","-pix_fmt",pix,"-y",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();'''
    new='''    let pix=if e.mode=="screen"{"rgb24"}else{"argb"};\n    let fps_s=if fps>=50{"60".to_string()}else{"30".to_string()};\n    let args=vec!["-hide_banner","-loglevel","error","-i",e.source.as_str(),"-vf",vf.as_str(),"-an","-c:v","qtrle","-pix_fmt",pix,"-fps_mode","cfr","-r",fps_s.as_str(),"-video_track_timescale","60000","-y",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();'''
    must(old in c,'Effects cache encode marker missing')
    c=c.replace(old,new,1)
must('"-fps_mode","cfr","-r",fps_s.as_str()' in c,'Effects cache CFR output missing')
p.write_text(c,encoding='utf-8')

print('ENDLUME 8.43 real CFR 30/60 output guard applied')
