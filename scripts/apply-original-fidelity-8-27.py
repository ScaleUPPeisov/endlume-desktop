from pathlib import Path
import re

p = Path('src-tauri/src/render.rs')
text = p.read_text(encoding='utf-8')

marker = 'fn smart_repeat_project(job:&QueueJob)->bool{job.project.media.len()==1&&job.project.media.iter().all(|m|is_image(m))}\n'
if marker not in text:
    raise SystemExit('8.27: smart_repeat_project marker not found; apply 8.26 first')

helpers = r'''
async fn choose_fidelity_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {
    if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}
  }
  "libx265".into()
}

fn fidelity_video_args(encoder:&str,s:&RenderSettings)->Vec<String>{
  let g=(s.fps.max(1)*10).to_string();
  let raw:Vec<&str>=match encoder{
    "hevc_videotoolbox"=>vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-q:v","95","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"],
    "h264_videotoolbox"=>vec!["-c:v","h264_videotoolbox","-realtime","1","-prio_speed","1","-power_efficient","0","-q:v","95","-g",&g,"-pix_fmt","yuv420p"],
    "libx265"=>vec!["-c:v","libx265","-preset","ultrafast","-crf","14","-tune","ssim","-g",&g,"-pix_fmt","yuv420p"],
    _=>vec!["-c:v","libx264","-preset","ultrafast","-crf","12","-tune","stillimage","-g",&g,"-keyint_min",&g,"-sc_threshold","0","-pix_fmt","yuv420p"],
  };
  raw.into_iter().map(String::from).collect()
}

async fn probe_audio_signature(app:&AppHandle,path:&str)->Result<(String,u32,u32),String>{
  let args=vec!["-v","error","-select_streams","a:0","-show_entries","stream=codec_name,sample_rate,channels","-of","csv=p=0:s=|",path].into_iter().map(String::from).collect();
  let (stdout,_)=output(app,"ffprobe",args).await?;
  let line=String::from_utf8_lossy(&stdout).trim().to_string();
  let parts=line.split('|').collect::<Vec<_>>();
  if parts.len()<3{return Err(format!("Не удалось прочитать параметры аудио: {path}"))}
  let rate=parts[1].parse::<u32>().map_err(|_|format!("Не удалось прочитать sample rate: {path}"))?;
  let channels=parts[2].parse::<u32>().map_err(|_|format!("Не удалось прочитать channels: {path}"))?;
  Ok((parts[0].to_string(),rate,channels))
}

fn ffconcat_escape(path:&Path)->String{
  let s=path.to_string_lossy().replace('\\',"/");
  let mut out=String::with_capacity(s.len()+8);
  for c in s.chars(){
    if matches!(c,' '|'\''|'#'){out.push('\\')}
    out.push(c);
  }
  out
}

async fn build_original_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
  if job.project.audio.is_empty(){return Err("Нет песен".into())}
  let mut durations=Vec::new();
  for a in &job.project.audio{durations.push(probe_duration(app,a).await.unwrap_or(180.0).max(0.2));}
  let mut first:Option<(String,u32,u32)>=None;
  for a in &job.project.audio{
    if !a.to_ascii_lowercase().ends_with(".mp3"){return Err(format!("{} — не MP3",Path::new(a).file_name().and_then(|x|x.to_str()).unwrap_or(a)))}
    let sig=probe_audio_signature(app,a).await?;
    if sig.0!="mp3"{return Err(format!("{} — codec {}",Path::new(a).file_name().and_then(|x|x.to_str()).unwrap_or(a),sig.0))}
    if let Some(ref base)=first{
      if base!=&sig{return Err(format!("MP3 имеют разные параметры: ожидается {} Hz / {} ch, найдено {} Hz / {} ch",base.1,base.2,sig.1,sig.2))}
    }else{first=Some(sig)}
  }
  let list=work.join("audio-original.ffconcat");
  let mut body=String::from("ffconcat version 1.0\n");
  for a in &job.project.audio{body.push_str(&format!("file {}\n",ffconcat_escape(Path::new(a))));}
  std::fs::write(&list,body).map_err(|e|format!("Original Audio: не удалось создать playlist: {e}"))?;
  let cycle=work.join("audio-original.mp3");
  let expected=durations.iter().sum::<f64>().max(0.2);
  let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-map","0:a:0","-c:a","copy","-fflags","+genpts","-avoid_negative_ts","make_zero","-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  run_ffmpeg(app,job,started,timer,args,"Original Audio: копирую MP3 без перекодирования",35.0,8.0,expected,encoder,attempt,cancel).await?;
  let cycle_duration=probe_duration(app,cycle.to_string_lossy().as_ref()).await.unwrap_or(expected);
  Ok((cycle,durations,cycle_duration))
}

async fn build_lossless_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
  if job.project.audio.is_empty(){return Err("Нет песен".into())}
  let mut durations=Vec::new();let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
  for a in &job.project.audio{
    durations.push(probe_duration(app,a).await.unwrap_or(180.0).max(0.2));
    args.extend(vec!["-i",a.as_str()].into_iter().map(String::from));
  }
  let mut graph=String::new();
  for i in 0..job.project.audio.len(){
    if i>0{graph.push(';')}
    graph.push_str(&format!("[{i}:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a{i}]"));
  }
  let inputs=(0..job.project.audio.len()).map(|i|format!("[a{i}]")).collect::<String>();
  graph.push_str(&format!(";{inputs}concat=n={}:v=0:a=1[outa]",job.project.audio.len()));
  let cycle=work.join("audio-lossless.m4a");let expected=durations.iter().sum::<f64>().max(0.2);
  args.extend(vec!["-filter_complex",&graph,"-map","[outa]","-c:a","alac","-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"Original Audio: ALAC lossless fallback",35.0,12.0,expected,encoder,attempt,cancel).await?;
  let cycle_duration=probe_duration(app,cycle.to_string_lossy().as_ref()).await.unwrap_or(expected);
  Ok((cycle,durations,cycle_duration))
}
'''

if 'fn fidelity_video_args(' not in text:
    text = text.replace(marker, marker + helpers, 1)

text = text.replace('args.extend(static_smart_encoder_args(s));', 'args.extend(fidelity_video_args(encoder,s));')
text = text.replace(
    'args.extend(encoder_args(encoder,&job.settings,smart));',
    'args.extend(if smart{fidelity_video_args(encoder,&job.settings)}else{encoder_args(encoder,&job.settings,false)});'
)
text = text.replace(
    'args.extend(encoder_args(encoder,&job.settings,smart_repeat_project(job)));',
    'args.extend(if smart_repeat_project(job){fidelity_video_args(encoder,&job.settings)}else{encoder_args(encoder,&job.settings,false)});'
)

old_select = 'let _=std::fs::remove_file(&out);let encoder=if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};\n    let smart_repeat=smart_repeat_project(job);\n    let _=app.emit("engine-profile",json!({"id":job.project.id,"smartSize":smart_repeat,"smartRepeat":smart_repeat,"targetVideoKbps":if smart_repeat{Some(static_video_kbps(&job.settings))}else{None::<u64>}}));'
new_select = 'let smart_repeat=smart_repeat_project(job);let _=std::fs::remove_file(&out);let encoder=if smart_repeat{choose_fidelity_encoder(app,attempt).await}else if attempt==1{choose_encoder(app,&job.settings).await}else{software_encoder(&job.settings)};\n    let _=app.emit("engine-profile",json!({"id":job.project.id,"smartSize":smart_repeat,"smartRepeat":smart_repeat,"originalFidelity":smart_repeat,"targetVideoKbps":None::<u64>}));'
if old_select not in text and 'originalFidelity":smart_repeat' not in text:
    raise SystemExit('8.27: render encoder/profile marker not found')
text = text.replace(old_select,new_select,1)

old_audio = '''      let (cycle,durations,cycle_duration)=build_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
      let target=job.settings.duration_hours*3600.0;let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,&job.settings.duration_mode);
      let audio=build_long_audio(app,job,started,&timer,&work,&cycle,cycle_duration,final_duration,&encoder,attempt,&cancel).await?;'''
new_audio = '''      let target=job.settings.duration_hours*3600.0;
      let (audio,durations,final_duration)=if smart_repeat{
        if job.settings.crossfade_sec>0.01||job.settings.normalize_lufs||job.ambient.as_ref().map(|x|!x.trim().is_empty()).unwrap_or(false){
          emit_warning(app,&job.project.id,"Original Fidelity: чтобы не портить музыку, кроссфейд, LUFS-нормализация и ambient для этого рендера не применяются.");
        }
        match build_original_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await{
          Ok((cycle,durations,_cycle_duration))=>{
            let final_duration=smart_final_duration(target,&durations,0.0,&job.settings.duration_mode);
            let _=app.emit("engine-profile",json!({"id":job.project.id,"audioOriginal":true,"audioLossless":false}));
            (AudioSource::Loop(cycle),durations,final_duration)
          },
          Err(reason)=>{
            emit_warning(app,&job.project.id,&format!("Точный MP3 stream-copy невозможен ({reason}). Перехожу на ALAC: без повторного lossy-сжатия, но файл может быть больше 1 ГБ."));
            let (cycle,durations,_cycle_duration)=build_lossless_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
            let final_duration=smart_final_duration(target,&durations,0.0,&job.settings.duration_mode);
            let _=app.emit("engine-profile",json!({"id":job.project.id,"audioOriginal":false,"audioLossless":true}));
            (AudioSource::Loop(cycle),durations,final_duration)
          }
        }
      }else{
        let (cycle,durations,cycle_duration)=build_audio_cycle(app,job,started,&timer,&work,&encoder,attempt,&cancel).await?;
        let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,&job.settings.duration_mode);
        let audio=build_long_audio(app,job,started,&timer,&work,&cycle,cycle_duration,final_duration,&encoder,attempt,&cancel).await?;
        (audio,durations,final_duration)
      };'''
if old_audio not in text and 'build_original_audio_cycle(app,job' not in text:
    raise SystemExit('8.27: render audio block not found')
text = text.replace(old_audio,new_audio,1)

text = text.replace(
    'let mut t=0.0;let mut i=0usize;let cf=job.settings.crossfade_sec.max(0.0);',
    'let mut t=0.0;let mut i=0usize;let cf=if smart_repeat_project(job){0.0}else{job.settings.crossfade_sec.max(0.0)};'
)

required=[
    'fn fidelity_video_args(',
    'build_original_audio_cycle(',
    'Original Audio: копирую MP3 без перекодирования',
    '"-c:a","copy"',
    '"-c:a","alac"',
    'choose_fidelity_encoder(app,attempt).await',
    '"originalFidelity":smart_repeat',
    '"audioOriginal":true',
    'fidelity_video_args(encoder,&job.settings)',
]
for m in required:
    if m not in text:
        raise SystemExit(f'8.27 validation failed: missing {m}')

p.write_text(text,encoding='utf-8')
print('ENDLUME alpha.8.27 Original Fidelity patch applied')
