from pathlib import Path
import re

p=Path('src-tauri/src/render.rs')
text=p.read_text(encoding='utf-8')

# 1. Output extension helper: Original Fidelity uses QuickTime MOV so exact MP3
# remains directly playable on macOS without a second lossy audio encode.
old_unique='fn unique_output(dir:&Path,name:&str)->PathBuf{let safe=safe_name(name);let mut p=dir.join(format!("{} — Ready Videos.mp4",safe));let mut n=2;while p.exists(){p=dir.join(format!("{} — Ready Videos_{}.mp4",safe,n));n+=1}p}\n'
new_unique=old_unique+'fn unique_output_ext(dir:&Path,name:&str,ext:&str)->PathBuf{let safe=safe_name(name);let ext=ext.trim_start_matches(\'.\');let mut p=dir.join(format!("{} — Ready Videos.{}",safe,ext));let mut n=2;while p.exists(){p=dir.join(format!("{} — Ready Videos_{}.{}",safe,n,ext));n+=1}p}\n'
if 'fn unique_output_ext(' not in text:
    if old_unique not in text: raise SystemExit('8.28: unique_output marker missing')
    text=text.replace(old_unique,new_unique,1)

# 2. Hybrid short-master encoder. Unlike 8.27 q:v 95 VideoToolbox, this does
# not create a 15-20 Mbit/s two-hour file. We encode only a short repeating
# master with x265 CRF14, then repeat it via stream-copy. Static pixels and small
# overlays compress extremely efficiently while avoiding the old 0.5-0.7 Mbit/s
# hard clamp that damaged the first frame/effect.
marker='async fn probe_audio_signature(app:&AppHandle,path:&str)->Result<(String,u32,u32),String>{\n'
helpers=r'''fn hybrid_master_seconds(_s:&RenderSettings)->f64{30.0}

fn hybrid_fidelity_args(s:&RenderSettings)->Vec<String>{
  let g=(s.fps.max(1)*30).to_string();
  let x265=format!("keyint={}:min-keyint={}:scenecut=0:open-gop=0",g,g);
  vec!["-c:v","libx265","-preset","ultrafast","-crf","14","-tune","ssim","-x265-params",&x265,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
}

async fn probe_audio_decodes(app:&AppHandle,path:&Path)->bool{
  let args=vec!["-v","error","-i",path.to_string_lossy().as_ref(),"-map","0:a:0","-t","1.0","-f","null","-"].into_iter().map(String::from).collect();
  output(app,"ffmpeg",args).await.is_ok()
}

'''
if 'fn hybrid_fidelity_args(' not in text:
    if marker not in text: raise SystemExit('8.28: fidelity helper marker missing')
    text=text.replace(marker,helpers+marker,1)

# 3. Rebuild the exact-MP3 cycle without broken DTS. Every source MP3 is first
# remuxed with stream-copy to strip ID3/Xing metadata, then concatf treats the
# cleaned files as one continuous raw MP3 stream. No audio samples are decoded or
# re-encoded. This fixes the silent QuickTime result and non-monotonic DTS warning.
pattern=r'async fn build_original_audio_cycle\(.*?\n}\n\nasync fn build_lossless_audio_cycle'
replacement=r'''async fn build_original_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
  if job.project.audio.is_empty(){return Err("Нет песен".into())}
  let mut durations=Vec::new();let mut first:Option<(String,u32,u32)>=None;let mut clean=Vec::new();
  for (i,a) in job.project.audio.iter().enumerate(){
    durations.push(probe_duration(app,a).await.unwrap_or(180.0).max(0.2));
    if !a.to_ascii_lowercase().ends_with(".mp3"){return Err(format!("{} — не MP3",Path::new(a).file_name().and_then(|x|x.to_str()).unwrap_or(a)))}
    let sig=probe_audio_signature(app,a).await?;
    if sig.0!="mp3"{return Err(format!("{} — codec {}",Path::new(a).file_name().and_then(|x|x.to_str()).unwrap_or(a),sig.0))}
    if let Some(ref base)=first{if base!=&sig{return Err(format!("MP3 имеют разные параметры: ожидается {} Hz / {} ch, найдено {} Hz / {} ch",base.1,base.2,sig.1,sig.2))}}else{first=Some(sig)}
    let dst=work.join(format!("audio-clean-{i:03}.mp3"));
    let args=vec!["-hide_banner","-loglevel","error","-i",a.as_str(),"-map","0:a:0","-c:a","copy","-map_metadata","-1","-write_xing","0","-id3v2_version","0","-y",dst.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
    output(app,"ffmpeg",args).await.map_err(|e|format!("Original Audio clean-remux: {e}"))?;clean.push(dst);
  }
  let raw_list=work.join("audio-raw-list.txt");
  let body=clean.iter().map(|p|p.to_string_lossy().into_owned()).collect::<Vec<_>>().join("\n");std::fs::write(&raw_list,body).map_err(|e|e.to_string())?;
  let cycle=work.join("audio-original-clean.mp3");let input=format!("concatf:{}",raw_list.to_string_lossy());let expected=durations.iter().sum::<f64>().max(0.2);
  let args=vec!["-hide_banner","-loglevel","error","-fflags","+genpts","-i",&input,"-map","0:a:0","-c:a","copy","-map_metadata","-1","-write_xing","0","-id3v2_version","0","-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  run_ffmpeg(app,job,started,timer,args,"Original Audio: MP3 bitstream-copy + новые таймстампы",35.0,8.0,expected,encoder,attempt,cancel).await?;
  if !probe_audio_decodes(app,&cycle).await{return Err("Original Audio: очищенный MP3 не декодируется".into())}
  let cycle_duration=probe_duration(app,cycle.to_string_lossy().as_ref()).await.unwrap_or(expected);
  Ok((cycle,durations,cycle_duration))
}

async fn build_lossless_audio_cycle'''
new_text,n=re.subn(pattern,replacement,text,count=1,flags=re.S)
if n!=1:
    if 'audio-original-clean.mp3' not in text: raise SystemExit(f'8.28: original audio function replacement failed ({n})')
else:text=new_text

# 4. One-image projects no longer pre-encode the background. The original image
# itself becomes the master source, eliminating a needless generation loss and
# several seconds of work.
master_sig='async fn build_source_master(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,f64),String>{\n'
master_insert='  if smart_repeat_project(job)&&job.project.media.len()==1&&is_image(&job.project.media[0]){emit_timing(app,&job.project.id,"master-loop",0.0);return Ok((PathBuf::from(&job.project.media[0]),hybrid_master_seconds(&job.settings)))}\n'
if master_insert.strip() not in text:
    if master_sig not in text: raise SystemExit('8.28: build_source_master marker missing')
    text=text.replace(master_sig,master_sig+master_insert,1)

# 5. Smart-repeat variants are rendered once directly from the ORIGINAL image +
# lossless overlay cache, then the 30-second HEVC master is repeated with copy.
variant_pat=r'async fn build_variant\(.*?\n}\n\nasync fn build_audio_cycle'
variant_new=r'''async fn build_variant(app:&AppHandle,job:&QueueJob,source_master:&Path,master_duration:f64,effects:&[EffectPreset],work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,variant_no:usize,started:i64,timer:&Instant)->Result<PathBuf,String>{
  let smart=smart_repeat_project(job)&&job.project.media.len()==1&&is_image(&job.project.media[0]);
  if effects.is_empty()&&!smart{return Ok(source_master.to_path_buf())}
  let out=work.join(format!("variant-{variant_no:03}.mp4"));let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();let input_start;
  let base_graph:String;
  if smart{
    args.extend(vec!["-loop","1","-framerate",&job.settings.fps.to_string(),"-i",job.project.media[0].as_str()].into_iter().map(String::from));input_start=1;base_graph=format!("{}[b0]",base_filter(&job.settings,"0:v"));
  }else{
    args.extend(vec!["-stream_loop","-1","-i",source_master.to_string_lossy().as_ref()].into_iter().map(String::from));input_start=1;base_graph="[0:v]setpts=PTS-STARTPTS[b0]".into();
  }
  for e in effects{args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}
  let (graph,last)=apply_effects_filter(base_graph,"b0".into(),effects,&job.settings,input_start);let graph=format!("{graph};[{last}]format=yuv420p[outv]");
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t",&master_duration.to_string(),"-an"].into_iter().map(String::from));
  if smart{args.extend(hybrid_fidelity_args(&job.settings));}else{args.extend(encoder_args(encoder,&job.settings,false));}
  args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"Hybrid Fidelity: собираю короткий master",32.0,3.0,master_duration,encoder,attempt,cancel).await?;Ok(out)
}

async fn build_audio_cycle'''
new_text,n=re.subn(variant_pat,variant_new,text,count=1,flags=re.S)
if n!=1:
    if 'Hybrid Fidelity: собираю короткий master' not in text: raise SystemExit(f'8.28: build_variant replacement failed ({n})')
else:text=new_text

# 6. Subscribe is only encoded for its short visible segments, with the same
# CRF14 x265 profile instead of VideoToolbox q95. This keeps the two-hour average
# size low without reducing the overlay to the old 0.6 Mbit/s budget.
old='args.extend(encoder_args(encoder,&job.settings,false));args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));run_ffmpeg(app,job,started,timer,args,"Добавляю Subscribe",base,span,len,encoder,attempt,cancel).await'
new='if smart_repeat_project(job){args.extend(hybrid_fidelity_args(&job.settings));}else{args.extend(encoder_args(encoder,&job.settings,false));}args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));run_ffmpeg(app,job,started,timer,args,"Добавляю Subscribe",base,span,len,encoder,attempt,cancel).await'
if old in text:text=text.replace(old,new,1)
elif new not in text:raise SystemExit('8.28: Subscribe encoder marker missing')

# 7. Original Fidelity uses a QuickTime MOV container. Apple documents MP3 as a
# QuickTime-supported sound format; MOV avoids the silent MP3-in-MP4 behavior
# seen in the user's 8.27 output. The MP3 stream itself is still copied.
old_out='let started=chrono::Utc::now().timestamp_millis();let timer=Instant::now();let mut last_error=String::new();let out_dir=render_output_dir(app,job).await?;let out=unique_output(&out_dir,&job.project.name);'
new_out='let original_fidelity=smart_repeat_project(job);let started=chrono::Utc::now().timestamp_millis();let timer=Instant::now();let mut last_error=String::new();let out_dir=render_output_dir(app,job).await?;let out=if original_fidelity{unique_output_ext(&out_dir,&job.project.name,"mov")}else{unique_output(&out_dir,&job.project.name)};'
if old_out in text:text=text.replace(old_out,new_out,1)
elif new_out not in text:raise SystemExit('8.28: render output marker missing')

# Prefer x265 short-master for the smart project; VideoToolbox q95 was the source
# of the 14 GB result. Ordinary projects keep their existing encoder selection.
old_sel='let smart_repeat=smart_repeat_project(job);let _=std::fs::remove_file(&out);let encoder=if smart_repeat{choose_fidelity_encoder(app,attempt).await}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};'
new_sel='let smart_repeat=smart_repeat_project(job);let _=std::fs::remove_file(&out);let encoder=if smart_repeat{"libx265".to_string()}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};'
if old_sel in text:text=text.replace(old_sel,new_sel,1)
elif new_sel not in text:raise SystemExit('8.28: fidelity encoder selector marker missing')

# Regenerate audio timestamps while looping, then stream-copy both tracks. Add
# faststart for immediate QuickTime playback.
text=text.replace('AudioSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))','AudioSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))')
old_mux='args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));'
new_mux='args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-movflags","+faststart","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));'
if old_mux in text:text=text.replace(old_mux,new_mux,1)
elif new_mux not in text:raise SystemExit('8.28: final mux marker missing')

# Final verification now checks that the audio track can actually be decoded,
# not merely that ffprobe sees an audio stream.
old_verify='if !probe_has_audio(app,out).await{return Err("В финальном файле отсутствует аудиодорожка".into())}'
new_verify=old_verify+'if !probe_audio_decodes(app,out).await{return Err("Аудиодорожка есть, но не воспроизводится/не декодируется".into())}'
if new_verify not in text:
    if old_verify not in text:raise SystemExit('8.28: final audio verification marker missing')
    text=text.replace(old_verify,new_verify,1)

required=[
 'fn hybrid_fidelity_args(', 'audio-original-clean.mp3','concatf:',
 'Hybrid Fidelity: собираю короткий master','unique_output_ext(&out_dir,&job.project.name,"mov")',
 '"libx265".to_string()','Аудиодорожка есть, но не воспроизводится/не декодируется',
 '"-movflags","+faststart"'
]
for m in required:
    if m not in text: raise SystemExit(f'8.28 validation failed: missing {m}')

p.write_text(text,encoding='utf-8')
print('ENDLUME alpha.8.28 Hybrid Fidelity + exact MP3 MOV patch applied')
