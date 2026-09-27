from pathlib import Path
import re

p = Path('src-tauri/src/render.rs')
text = p.read_text(encoding='utf-8')

# This patch is intentionally applied AFTER apply-render-stability-8-25.py.
# It extends Smart Size to the user's dominant project shape:
# one still image + music + cached Effects/Subscribe.

if 'fn smart_repeat_project(' not in text:
    marker = 'fn software_encoder(s:&RenderSettings)->String{if s.codec.eq_ignore_ascii_case("h265"){"libx265".into()}else{"libx264".into()}}\n'
    insert = marker + '''fn smart_repeat_project(job:&QueueJob)->bool{job.project.media.len()==1&&job.project.media.iter().all(|m|is_image(m))}\n'''
    if marker not in text:
        raise SystemExit('8.26: software_encoder marker not found; apply 8.25 stability first')
    text = text.replace(marker, insert, 1)

# 700–1000 MB target for 2h including AAC 320k.
# 1080p: ~520k video + 320k audio => ~756 MB / 2h
# 1440p: ~600k video + 320k audio => ~828 MB / 2h
# 4K:    ~700k video + 320k audio => ~918 MB / 2h
text = text.replace('0..=1920=>450,\n    1921..=2560=>520,\n    _=>620,', '0..=1920=>520,\n    1921..=2560=>600,\n    _=>700,')

# A single still image must always use the short Smart Size master, even when
# Effects/Subscribe are enabled. Previously overlays disabled Smart Size and
# forced 20–30 Mbit/s for the entire 2h output.
old_media = 'if is_image(media) && total==1 && job.effects.iter().all(|e|!e.enabled) && job.subscribes.iter().all(|e|!e.effect.enabled){'
if old_media in text:
    text = text.replace(old_media, 'if is_image(media) && total==1{', 1)
elif 'if is_image(media) && total==1{' not in text:
    raise SystemExit('8.26: build_media_clip Smart Size condition not found')

# Full-length variants for a still-image project also use Smart Size bitrate.
# For video projects smart_repeat_project(job) is false, so the existing
# high-quality video path is unchanged.
needle = 'encoder_args(encoder,&job.settings,false)'
if needle in text:
    text = text.replace(needle, 'encoder_args(encoder,&job.settings,smart_repeat_project(job))')

# Avoid a second generation of compression for the base image when building a
# persistent Effect variant: feed the original still directly into the overlay
# compositor and encode it once.
variant_pattern = re.compile(
    r'''async fn build_variant\(app:&AppHandle,job:&QueueJob,source_master:&Path,master_duration:f64,effects:&\[EffectPreset\],work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,variant_no:usize,started:i64,timer:&Instant\)->Result<PathBuf,String>\{[\s\S]*?\n\}'''
)
match = variant_pattern.search(text)
if not match:
    raise SystemExit('8.26: build_variant block not found')
new_variant = r'''async fn build_variant(app:&AppHandle,job:&QueueJob,source_master:&Path,master_duration:f64,effects:&[EffectPreset],work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool,variant_no:usize,started:i64,timer:&Instant)->Result<PathBuf,String>{
  if effects.is_empty(){return Ok(source_master.to_path_buf())}
  let smart=smart_repeat_project(job);let out=work.join(format!("variant-{variant_no:03}.mp4"));let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();
  if smart{args.extend(vec!["-loop","1","-framerate",&job.settings.fps.to_string(),"-i",job.project.media[0].as_str()].into_iter().map(String::from));}
  else{args.extend(vec!["-stream_loop","-1","-i",source_master.to_string_lossy().as_ref()].into_iter().map(String::from));}
  for e in effects{args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}
  let initial=if smart{format!("{}[b0]",base_filter(&job.settings,"0:v"))}else{"[0:v]setpts=PTS-STARTPTS[b0]".into()};
  let (graph,last)=apply_effects_filter(initial,"b0".into(),effects,&job.settings,1);let graph=format!("{graph};[{last}]format=yuv420p[outv]");
  args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t",&master_duration.to_string(),"-an"].into_iter().map(String::from));args.extend(encoder_args(encoder,&job.settings,smart));args.extend(vec!["-progress","pipe:1","-y",out.to_string_lossy().as_ref()].into_iter().map(String::from));
  run_ffmpeg(app,job,started,timer,args,if smart{"Smart Repeat: кэширую Effects"}else{"Подготавливаю вариант Effects"},32.0,3.0,master_duration,encoder,attempt,cancel).await?;Ok(out)
}'''
text = text[:match.start()] + new_variant + text[match.end():]

# Keep the full period of a normal looping Effect (e.g. a 28 s circular
# animation) before repeating the master. This prevents a 12 s restart from
# changing the original animation timing.
if 'async fn smart_repeat_visual_seconds(' not in text:
    marker = 'fn smart_final_duration(target:f64,durations:&[f64],crossfade:f64,mode:&str)->f64'
    helper = '''async fn smart_repeat_visual_seconds(app:&AppHandle,base:f64,effects:&[EffectPreset])->f64{\n  let mut seconds=base.max(1.0);\n  for e in effects.iter().filter(|e|e.enabled&&!e.source.trim().is_empty()){\n    if let Ok(d)=probe_duration(app,&e.source).await{seconds=seconds.max(d.clamp(1.0,60.0));}\n  }\n  seconds\n}\n\n'''
    if marker not in text:
        raise SystemExit('8.26: smart_final_duration marker not found')
    text = text.replace(marker, helper + marker, 1)

# Render profile and visual planner now recognise still+overlay as Smart Repeat.
old_profile = 'let pure_static=job.project.media.iter().all(|m|is_image(m))&&job.effects.iter().all(|e|!e.enabled)&&job.subscribes.iter().all(|e|!e.effect.enabled);\n    let _=app.emit("engine-profile",json!({"id":job.project.id,"smartSize":pure_static,"targetVideoKbps":if pure_static{Some(static_video_kbps(&job.settings))}else{None::<u64>}}));'
new_profile = 'let smart_repeat=smart_repeat_project(job);\n    let _=app.emit("engine-profile",json!({"id":job.project.id,"smartSize":smart_repeat,"smartRepeat":smart_repeat,"targetVideoKbps":if smart_repeat{Some(static_video_kbps(&job.settings))}else{None::<u64>}}));'
if old_profile in text:
    text = text.replace(old_profile, new_profile, 1)
elif '"smartRepeat":smart_repeat' not in text:
    raise SystemExit('8.26: render profile marker not found')

old_prepare = 'let (fx,subs)=prepare_overlays(app,job,started,&timer,&encoder,attempt).await?;\n      let (cycle,durations,cycle_duration)=build_audio_cycle'
new_prepare = 'let (fx,subs)=prepare_overlays(app,job,started,&timer,&encoder,attempt).await?;\n      let visual_master_duration=if smart_repeat{smart_repeat_visual_seconds(app,master_duration,&fx).await}else{master_duration};\n      let (cycle,durations,cycle_duration)=build_audio_cycle'
if old_prepare in text:
    text = text.replace(old_prepare, new_prepare, 1)
elif 'let visual_master_duration=if smart_repeat' not in text:
    raise SystemExit('8.26: prepare_overlays render marker not found')

old_assemble = 'assemble_visual(app,job,&source_master,master_duration,&fx,&subs,final_duration,&work,&encoder,attempt,&cancel,started,&timer).await?;'
new_assemble = 'assemble_visual(app,job,&source_master,visual_master_duration,&fx,&subs,final_duration,&work,&encoder,attempt,&cancel,started,&timer).await?;'
if old_assemble in text:
    text = text.replace(old_assemble, new_assemble, 1)
elif new_assemble not in text:
    raise SystemExit('8.26: assemble_visual call marker not found')

# Guardrails: do not silently ship the old 20 Mbit/s path for a still project.
required = [
    'fn smart_repeat_project(',
    'if is_image(media) && total==1{',
    'encoder_args(encoder,&job.settings,smart)',
    'let visual_master_duration=if smart_repeat',
    '"smartRepeat":smart_repeat',
    '_=>700,',
]
for marker in required:
    if marker not in text:
        raise SystemExit(f'8.26 validation failed: missing {marker}')

p.write_text(text, encoding='utf-8')
print('ENDLUME alpha.8.26 Smart Repeat patch applied')
