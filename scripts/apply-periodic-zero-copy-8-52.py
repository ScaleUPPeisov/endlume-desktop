#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit('8.52: missing '+rel)
    return p
def must(c,m):
    if not c: raise SystemExit('8.52: '+m)

p=need('src-tauri/src/render.rs');s=p.read_text(encoding='utf-8')

# Keep the visually proven Apple Silicon q100 path. 500k is only the target;
# VideoToolbox is allowed to spend bits on complex overlay frames because the
# zero-copy movie manifest removes repeated physical payload instead.
a=s.find('fn hybrid_fidelity_args(');b=s.find('\n\nasync fn choose_hybrid_encoder',a)
must(a>=0 and b>a,'hybrid_fidelity_args not found')
new_args=r'''fn hybrid_fidelity_args(s:&RenderSettings,encoder:&str,duration:f64)->Vec<String>{
  let frames=(s.fps.max(1) as f64*duration.max(2.0)).round().max(1.0) as u32;
  let g=frames.to_string();
  if encoder=="libx265"{
    let x265=format!("keyint={}:min-keyint={}:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0",g,g);
    vec!["-c:v","libx265","-preset","ultrafast","-crf","18","-maxrate","500k","-bufsize","4M","-x265-params",&x265,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }else{
    vec!["-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M","-g",&g,"-tag:v","hvc1","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()
  }
}'''
s=s[:a]+new_args+s[b:]
a=s.find('async fn choose_hybrid_encoder(');b=s.find('\n\nasync fn probe_audio_decodes',a)
must(a>=0 and b>a,'choose_hybrid_encoder not found')
new_choose=r'''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  if encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  "libx265".into()
}'''
s=s[:a]+new_choose+s[b:]

anchor='pub async fn render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<(),String>{'
must(anchor in s,'render_job anchor missing')
helpers=r'''
#[derive(Clone)]
struct Periodic852Plan{first_frames:usize,anchor_frames:usize,repeat_frames:usize,master_frames:usize,sub:SubscribePreset}

fn periodic_852_plan(job:&QueueJob,effects:&[EffectPreset],subs:&[SubscribePreset],final_duration:f64)->Option<Periodic852Plan>{
  if !smart_repeat_project(job)||timed_effects(effects,final_duration){return None}
  let active=subs.iter().filter(|x|x.effect.enabled&&!x.effect.source.trim().is_empty()).collect::<Vec<_>>();
  if active.len()!=1{return None}
  let sub=active[0];if sub.effect.mode=="screen"||sub.effect.mode=="screen-cache"||sub.repeat_every_sec<60.0{return None}
  let fps=job.settings.fps.max(1) as f64;let first=sub.first_at_sec.min(sub.second_at_sec).max(0.0);let anchor=sub.first_at_sec.max(sub.second_at_sec).max(0.0);
  let first_frames=(first*fps).round() as usize;let anchor_frames=(anchor*fps).round() as usize;let repeat_frames=(sub.repeat_every_sec*fps).round() as usize;
  if repeat_frames==0||anchor_frames==0{return None}
  let desired=(30.0*fps).round() as usize;let lo=(20.0*fps).round() as usize;let hi=(40.0*fps).round() as usize;
  let mut best=None::<usize>;let mut best_dist=usize::MAX;
  for d in lo.max(1)..=hi.max(lo.max(1)){if repeat_frames%d==0{let dist=d.abs_diff(desired);if dist<best_dist{best=Some(d);best_dist=dist}}}
  let master_frames=best?;
  // The common ENDLUME schedule (10s/20s/300s) stays inside the first master.
  // More exotic schedules keep the proven 8.51 planner instead of being guessed at.
  if anchor_frames>=master_frames||first_frames>anchor_frames{return None}
  Some(Periodic852Plan{first_frames,anchor_frames,repeat_frames,master_frames,sub:sub.clone()})
}

async fn probe_video_frames_852(app:&AppHandle,path:&Path)->Result<usize,String>{
  let args=vec!["-v","error","-count_frames","-select_streams","v:0","-show_entries","stream=nb_read_frames","-of","default=nw=1:nk=1",path.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  let (o,_)=output(app,"ffprobe",args).await?;String::from_utf8_lossy(&o).trim().parse::<usize>().map_err(|_|format!("Не удалось посчитать кадры: {}",path.display()))
}

async fn build_periodic_master_852(app:&AppHandle,job:&QueueJob,effects:&[EffectPreset],plan:&Periodic852Plan,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<PathBuf,String>{
  let out=work.join("periodic-852-master.mp4");let fps=job.settings.fps.max(1);let work_fps=if fps>=50{30}else{fps};let duration=plan.master_frames as f64/fps as f64;
  let mut ws=job.settings.clone();ws.fps=work_fps;
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",&work_fps.to_string(),"-i",job.project.media[0].as_str()].into_iter().map(String::from).collect();
  for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}
  let base=format!("{}[b0]",base_filter(&ws,"0:v"));let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps={fps},format=yuv420p[outv]");
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-frames:v",&plan.master_frames.to_string(),"-an"].into_iter().map(String::from));args.extend(hybrid_fidelity_args(&job.settings,encoder,duration));args.extend(vec!["-fps_mode","cfr","-r",&fps.to_string(),"-video_track_timescale","60000","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"8.52: собираю 30-секундный fidelity master",58.0,10.0,duration,encoder,attempt,cancel).await?;
  let frames=probe_video_frames_852(app,&out).await?;if frames!=plan.master_frames{return Err(format!("8.52 master: {} кадров вместо {}",frames,plan.master_frames))}Ok(out)
}

async fn copy_head_frames_852(app:&AppHandle,job:&QueueJob,src:&Path,frames:usize,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<(),String>{
  if frames==0{return Err("8.52: zero-frame head requested".into())}
  let args=vec!["-hide_banner","-loglevel","error","-i",src.to_string_lossy().as_ref(),"-map","0:v:0","-frames:v",&frames.to_string(),"-an","-c:v","copy","-avoid_negative_ts","make_zero","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();
  run_ffmpeg(app,job,started,timer,args,"8.52: готовлю zero-copy video slice",68.0,1.0,frames as f64/job.settings.fps.max(1) as f64,encoder,attempt,cancel).await?;let got=probe_video_frames_852(app,out).await?;if got!=frames{return Err(format!("8.52 slice: {got} кадров вместо {frames}"))}Ok(())
}

async fn render_periodic_sub_852(app:&AppHandle,job:&QueueJob,master:&Path,sub:&SubscribePreset,start_frame:usize,frames:usize,work:&Path,label:&str,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<PathBuf,String>{
  let fps=job.settings.fps.max(1);let work_fps=if fps>=50{30}else{fps};let phase=start_frame as f64/fps as f64;let out=work.join(format!("periodic-852-sub-{label}.mp4"));let mut ws=job.settings.clone();ws.fps=work_fps;
  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&phase.to_string(),"-i",master.to_string_lossy().as_ref(),"-i",sub.effect.source.as_str()].into_iter().map(String::from).collect();
  let one=vec![sub.effect.clone()];let (graph,last)=apply_effects_filter(format!("[0:v]fps={work_fps},setpts=PTS-STARTPTS[b0]"),"b0".into(),&one,&ws,1);let graph=graph.replace(":shortest=1:eof_action=repeat",":shortest=0:eof_action=pass");let graph=format!("{graph};[{last}]fps={fps},format=yuv420p[outv]");
  let duration=frames as f64/fps as f64;args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-frames:v",&frames.to_string(),"-an"].into_iter().map(String::from));args.extend(hybrid_fidelity_args(&job.settings,encoder,duration));args.extend(vec!["-fps_mode","cfr","-r",&fps.to_string(),"-video_track_timescale","60000","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,"8.52: добавляю Subscribe один раз на цикл",69.0,4.0,duration,encoder,attempt,cancel).await?;let got=probe_video_frames_852(app,&out).await?;if got!=frames{return Err(format!("8.52 Subscribe: {got} кадров вместо {frames}"))}Ok(out)
}

async fn concat_video_parts_852(app:&AppHandle,job:&QueueJob,parts:&[PathBuf],out:&Path,expected_frames:usize,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<(),String>{
  let list=work.join("periodic-852-video-list.txt");let body=parts.iter().map(|x|format!("file '{}'
",ffconcat_escape(x))).collect::<String>();std::fs::write(&list,body).map_err(|e|e.to_string())?;
  let args=vec!["-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",list.to_string_lossy().as_ref(),"-map","0:v:0","-an","-c:v","copy","-avoid_negative_ts","make_zero","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect();run_ffmpeg(app,job,started,timer,args,"8.52: собираю один физический 300s video-cycle",74.0,3.0,expected_frames as f64/job.settings.fps.max(1) as f64,encoder,attempt,cancel).await?;let got=probe_video_frames_852(app,out).await?;if got!=expected_frames{return Err(format!("8.52 seed video: {got} кадров вместо {expected_frames}"))}Ok(())
}

async fn render_periodic_zero_copy_852(app:&AppHandle,job:&QueueJob,effects:&[EffectPreset],subs:&[SubscribePreset],audio:&AudioSource,final_duration:f64,work:&Path,out:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,started:i64,timer:&Instant)->Result<bool,String>{
  let Some(plan)=periodic_852_plan(job,effects,subs,final_duration) else{return Ok(false)};let fps=job.settings.fps.max(1) as usize;let sub_d=probe_duration(app,&plan.sub.effect.source).await.unwrap_or(0.0);let sub_frames=(sub_d*fps as f64).ceil().max(1.0) as usize;
  if plan.first_frames<plan.anchor_frames&&sub_frames>plan.anchor_frames-plan.first_frames{return Ok(false)}
  let master=build_periodic_master_852(app,job,effects,&plan,work,encoder,attempt,cancel,started,timer).await?;
  let mut prefix=Vec::<PathBuf>::new();
  if plan.first_frames<plan.anchor_frames{
    if plan.first_frames>0{let p=work.join("periodic-852-prefix-head.mp4");copy_head_frames_852(app,job,&master,plan.first_frames,&p,encoder,attempt,cancel,started,timer).await?;prefix.push(p)}
    let gap=plan.anchor_frames-plan.first_frames;let p=render_periodic_sub_852(app,job,&master,&plan.sub,plan.first_frames,gap,work,"first",encoder,attempt,cancel,started,timer).await?;prefix.push(p);
  }else if plan.anchor_frames>0{let p=work.join("periodic-852-prefix-head.mp4");copy_head_frames_852(app,job,&master,plan.anchor_frames,&p,encoder,attempt,cancel,started,timer).await?;prefix.push(p)}
  let phase=plan.anchor_frames%plan.master_frames;let mut cycle_sub=(plan.master_frames-phase)%plan.master_frames;if cycle_sub==0{cycle_sub=plan.master_frames}while cycle_sub<sub_frames{cycle_sub+=plan.master_frames}if cycle_sub>=plan.repeat_frames{return Ok(false)}
  let recurring=render_periodic_sub_852(app,job,&master,&plan.sub,phase,cycle_sub,work,"cycle",encoder,attempt,cancel,started,timer).await?;
  let mut parts=prefix;parts.push(recurring);let remain=plan.repeat_frames-cycle_sub;let full=remain/plan.master_frames;let tail=remain%plan.master_frames;for _ in 0..full{parts.push(master.clone())}if tail>0{let p=work.join("periodic-852-cycle-tail.mp4");copy_head_frames_852(app,job,&master,tail,&p,encoder,attempt,cancel,started,timer).await?;parts.push(p)}
  let seed_video=work.join("periodic-852-seed-video.mp4");let seed_frames=plan.anchor_frames+plan.repeat_frames;concat_video_parts_852(app,job,&parts,&seed_video,seed_frames,work,encoder,attempt,cancel,started,timer).await?;
  let seed=work.join("periodic-852-seed.mov");let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-i",seed_video.to_string_lossy().as_ref()].into_iter().map(String::from).collect();match audio{AudioSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))};args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-progress","pipe:1","-y",seed.to_string_lossy().as_ref()].into_iter().map(String::from));run_ffmpeg(app,job,started,timer,args,"8.52: mux seed без размножения video payload",78.0,8.0,final_duration,encoder,attempt,cancel).await?;
  let total_frames=(final_duration*fps as f64).round().max(seed_frames as f64) as usize;let manifest=work.join("periodic-852-final.mov");let mark=Instant::now();crate::mp4_manifest::expand_video_prefix_cycle(&seed,&manifest,plan.anchor_frames,plan.repeat_frames,total_frames)?;std::fs::rename(&manifest,out).map_err(|e|format!("8.52: не удалось завершить zero-copy MOV: {e}"))?;emit_timing(app,&job.project.id,"zero-copy-manifest",mark.elapsed().as_secs_f64());emit_progress(app,job,started,timer,96.0,"8.52 Zero-copy manifest готов",encoder,attempt,None);Ok(true)
}

'''
s=s.replace(anchor,helpers+anchor,1)

old='''      let visual=assemble_visual(app,job,&source_master,visual_master_duration,&fx,&subs,final_duration,&work,&encoder,attempt,&cancel,started,&timer).await?;
      let mux_mark=Instant::now();let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
      match visual{VisualSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),VisualSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),VisualSource::Concat(p)=>args.extend(vec!["-f","concat","-safe","0","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}
      match audio{AudioSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}
      args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-movflags","+faststart","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
      run_ffmpeg(app,job,started,&timer,args,"Собираю итоговое видео",90.0,6.0,final_duration,&encoder,attempt,&cancel).await?;
      emit_timing(app,&job.project.id,"final-mux",mux_mark.elapsed().as_secs_f64());emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&encoder,attempt,None);verify_result(app,&out,final_duration,&job.settings).await?;
'''
must(old in s,'final mux block not found')
new='''      let zero_copy=if smart_repeat{render_periodic_zero_copy_852(app,job,&fx,&subs,&audio,final_duration,&work,&out,&encoder,attempt,&cancel,started,&timer).await?}else{false};
      if !zero_copy{
        let visual=assemble_visual(app,job,&source_master,visual_master_duration,&fx,&subs,final_duration,&work,&encoder,attempt,&cancel,started,&timer).await?;
        let mux_mark=Instant::now();let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
        match visual{VisualSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),VisualSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),VisualSource::Concat(p)=>args.extend(vec!["-f","concat","-safe","0","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}
        match &audio{AudioSource::Loop(p)=>args.extend(vec!["-stream_loop","-1","-fflags","+genpts","-i",p.to_string_lossy().as_ref()].into_iter().map(String::from)),AudioSource::Long(p)=>args.extend(vec!["-i",p.to_string_lossy().as_ref()].into_iter().map(String::from))}
        args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-movflags","+faststart","-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
        run_ffmpeg(app,job,started,&timer,args,"Собираю итоговое видео",90.0,6.0,final_duration,&encoder,attempt,&cancel).await?;emit_timing(app,&job.project.id,"final-mux",mux_mark.elapsed().as_secs_f64());
      }
      emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&encoder,attempt,None);verify_result(app,&out,final_duration,&job.settings).await?;
'''
s=s.replace(old,new,1)

# Version every visible/runtime config consistently.
for rel in ['package.json','src-tauri/tauri.conf.json','src-tauri/Cargo.toml']:
    q=need(rel);x=q.read_text(encoding='utf-8').replace('1.0.0-alpha.8.51','1.0.0-alpha.8.52');q.write_text(x,encoding='utf-8')

for marker in ['Periodic852Plan','expand_video_prefix_cycle','8.52 Zero-copy manifest готов','"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"','attempt==1&&encoder_works(app,"hevc_videotoolbox")']:
    must(marker in s,'postcondition missing '+marker)
p.write_text(s,encoding='utf-8')
print('ENDLUME 8.52 periodic zero-copy render patch: PASS')
