from pathlib import Path
import re


def must(cond,msg):
    if not cond:
        raise SystemExit('8.43: '+msg)

p=Path('src-tauri/src/render.rs')
r=p.read_text(encoding='utf-8')

# Keep the user's actual mode. 8.36 clamped 60->30; 8.41 then hard-forced 60.
# 8.43 supports exactly two production modes: genuine CFR30 and genuine CFR60.
if 'resolved_job.settings.fps=60;' in r:
    r=r.replace('resolved_job.settings.fps=60;','resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};',1)
must('resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};' in r,'30/60 runtime normalization missing')
must('resolved_job.settings.fps=resolved_job.settings.fps.min(30);' not in r,'historical 60->30 clamp survived')

if 'fn cfr_output_args(' not in r:
    marker='fn base_filter(s:&RenderSettings,label:&str)->String{'
    must(marker in r,'base_filter marker missing')
    helper='''fn cfr_output_args(s:&RenderSettings)->Vec<String>{\n  let fps=if s.fps>=50{60}else{30};\n  vec!["-fps_mode".into(),"cfr".into(),"-r".into(),fps.to_string(),"-video_track_timescale".into(),"60000".into()]\n}\n\n'''
    r=r.replace(marker,helper+marker,1)

# Insert CFR output arguments structurally into the actual video-encoding functions.
# This is intentionally independent of hybrid_fidelity_args signature/version.
def guard_function(text,name,end_marker,settings_expr,required_marker=None):
    start=text.find(name)
    must(start>=0,f'{name} missing')
    end=text.find(end_marker,start)
    must(end>start,f'{name} end marker missing')
    body=text[start:end]
    if required_marker:
        must(required_marker in body,f'{name}: active encoder marker {required_marker} missing')
    if 'cfr_output_args(' not in body:
        progress='args.extend(vec!["-progress"'
        pos=body.find(progress)
        must(pos>=0,f'{name}: output progress marker missing')
        body=body[:pos]+f'args.extend(cfr_output_args({settings_expr}));'+body[pos:]
        text=text[:start]+body+text[end:]
    # Re-read body after possible replacement and prove the guard is inside this function.
    start=text.find(name)
    end=text.find(end_marker,start)
    body=text[start:end]
    must(f'cfr_output_args({settings_expr})' in body,f'{name}: CFR guard missing')
    return text

r=guard_function(r,'async fn encode_static_smart_clip(', '\n\nfn encoder_args(', 's')
r=guard_function(r,'async fn build_media_clip(', '\n\nasync fn build_source_master', 's')
r=guard_function(r,'async fn build_variant(', '\n\nasync fn build_audio_cycle', '&job.settings', 'hybrid_fidelity_args(')
r=guard_function(r,'async fn render_sub_segment(', '\n\nasync fn assemble_visual', '&job.settings')

must('fn cfr_output_args(' in r,'CFR helper missing')
must('Hybrid Fidelity: собираю короткий master' in r,'dominant Hybrid Fidelity short-master path missing')
must('fps={},setsar=1' in r,'base filter no longer derives FPS from RenderSettings')

# Final two-hour output stays stream-copy. Only normalize the video timescale so
# the already-CFR short-master cadence survives muxing without a full re-encode.
final_mux_plain='"-c:v","copy","-c:a","copy","-progress","pipe:1"'
final_mux_plain_new='"-c:v","copy","-c:a","copy","-video_track_timescale","60000","-progress","pipe:1"'
final_mux_fast='"-c:v","copy","-c:a","copy","-movflags","+faststart","-progress","pipe:1"'
final_mux_fast_new='"-c:v","copy","-c:a","copy","-video_track_timescale","60000","-movflags","+faststart","-progress","pipe:1"'
if final_mux_fast in r:
    r=r.replace(final_mux_fast,final_mux_fast_new,1)
elif final_mux_plain in r:
    r=r.replace(final_mux_plain,final_mux_plain_new,1)
must('"-c:v","copy","-c:a","copy","-video_track_timescale","60000"' in r,'final stream-copy mux timescale guard missing')

# Final-file hard guard: metadata + effective packet cadence must agree with the
# requested 30/60 mode. This runs on the exact file returned to the user.
start=r.find('async fn verify_result(')
end=r.find('\n\npub async fn render_job',start)
must(start>=0 and end>start,'verify_result helper missing')
new_verify=r'''async fn verify_result(app:&AppHandle,out:&Path,expected:f64,s:&RenderSettings)->Result<(),String>{
  let d=probe_duration(app,out.to_string_lossy().as_ref()).await?;
  if (d-expected).abs()>4.0{return Err(format!("Финальный файл имеет неверную длительность: {:0.1} сек вместо {:0.1}",d,expected))}
  if !probe_has_audio(app,out).await{return Err("В финальном файле отсутствует аудиодорожка".into())}
  if !probe_audio_decodes(app,out).await{return Err("Аудиодорожка есть, но не воспроизводится/не декодируется".into())}
  let args=vec!["-v","error","-select_streams","v:0","-count_packets","-show_entries","stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_packets,duration","-of","json",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  let (stdout,_)=output(app,"ffprobe",args).await?;
  let v:serde_json::Value=serde_json::from_slice(&stdout).map_err(|e|e.to_string())?;
  let stream=v.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()).ok_or("FFprobe не вернул видеопоток")?;
  let w=stream.get("width").and_then(|x|x.as_u64()).unwrap_or(0) as u32;
  let h=stream.get("height").and_then(|x|x.as_u64()).unwrap_or(0) as u32;
  if w!=s.width||h!=s.height{return Err(format!("Неверное разрешение результата: {}x{} вместо {}x{}",w,h,s.width,s.height))}
  let parse_rate=|rate:&str|->f64{let mut it=rate.split('/');let n=it.next().and_then(|x|x.parse::<f64>().ok()).unwrap_or(0.0);let den=it.next().and_then(|x|x.parse::<f64>().ok()).unwrap_or(1.0).max(0.000001);n/den};
  let r_fps=parse_rate(stream.get("r_frame_rate").and_then(|x|x.as_str()).unwrap_or("0/1"));
  let a_fps=parse_rate(stream.get("avg_frame_rate").and_then(|x|x.as_str()).unwrap_or("0/1"));
  let wanted=if s.fps>=50{60.0}else{30.0};
  if (r_fps-wanted).abs()>0.10||(a_fps-wanted).abs()>0.10||(r_fps-a_fps).abs()>0.10{return Err(format!("Ошибка FPS: запрошено {:.0} FPS, финальный файл имеет r_frame_rate={:.3}, avg_frame_rate={:.3}",wanted,r_fps,a_fps))}
  let stream_d=stream.get("duration").and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok()).unwrap_or(d).max(0.001);
  let packets=stream.get("nb_read_packets").and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok()).or_else(||stream.get("nb_frames").and_then(|x|x.as_str()).and_then(|x|x.parse::<f64>().ok()));
  if let Some(frames)=packets{let measured=frames/stream_d;if (measured-wanted).abs()>0.20{return Err(format!("Ошибка FPS: запрошено {:.0} FPS, по фактическому числу видеопакетов финальный файл имеет {:.3} FPS",wanted,measured))}}
  Ok(())
}'''
r=r[:start]+new_verify+r[end:]

# Do not allow FPS work to change the accepted render contract.
must('fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' in r,'500k video budget changed')
must('"-maxrate","500k","-bufsize","4M"' in r,'x265 size guard changed')
must('"-b:v","500k","-maxrate","4M","-bufsize","16M"' in r,'VideoToolbox size guard changed')
must('force_original_aspect_ratio=increase' in r and 'crop={}:{}:(iw-ow)/2:(ih-oh)/2' in r,'1920x1080 cover/crop changed')
must('acrossfade=d={cf}:c1=tri:c2=tri' in r,'audio crossfade changed')
must('materialize_continuous_audio' in r,'gapless audio changed')
p.write_text(r,encoding='utf-8')

# Effects cache already gets true temporal 60 through minterpolate in 8.41;
# additionally force its MOV cache container to CFR30/CFR60.
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
