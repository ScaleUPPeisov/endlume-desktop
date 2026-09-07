#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'src-tauri/src/render.rs'
M=ROOT/'src-tauri/src/mp4_manifest.rs'
s=R.read_text(encoding='utf-8')
m=M.read_text(encoding='utf-8')

def once(text,old,new,label):
    n=text.count(old)
    if n!=1:
        raise SystemExit(f'8.60 migration: {label}: expected 1 anchor, found {n}')
    return text.replace(old,new,1)

# 8.60 is deliberately narrow: render speed stability only.
# Preserve VideoToolbox q:v100 / GOP1800 / 1920x1080 / CFR60 / MP3 packet copy.
for marker in [
    'const STRICT_857_MAX_GOP_FRAMES:u32=1800;',
    '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"',
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
]:
    if marker not in s: raise SystemExit('8.60 migration: missing invariant '+marker)

# Sustained physical benchmark: 8 filter threads are fastest on the target M1.
if '"-filter_complex_threads","8"' not in s:
    raise SystemExit('8.60 migration: strict 8-thread filter anchor missing')

# Optimization 1: pre-scale/crop the single static still once per job. -vf
# accepts an unlabeled chain, so strip only the source label from base_filter().
old='''  let master=work.join("strict-856-master.mp4");let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-filter_complex_threads","8","-loop","1","-framerate","30","-i",job.project.media[0].as_str()].into_iter().map(String::from).collect();for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base=format!("{}[b0]",base_filter(&ws,"0:v"));let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps=60,format=yuv420p[outv]");'''
new='''  let base_still=work.join("strict-860-base.png");\n  if !base_still.is_file(){\n    let vf=base_filter(&ws,"0:v");\n    let vf=vf.trim_start_matches("[0:v]").to_string();\n    let prep=vec!["-hide_banner","-loglevel","error","-i",job.project.media[0].as_str(),"-vf",vf.as_str(),"-frames:v","1","-compression_level","1","-y",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n    output(app,"ffmpeg",prep).await.map_err(|e|format!("Strict 8.60 static base preprocess: {e}"))?;\n  }\n  let master=work.join("strict-856-master.mp4");let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-filter_complex_threads","8","-loop","1","-framerate","30","-i",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base="[0:v]fps=30,setsar=1[b0]".to_string();let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps=60,format=yuv420p[outv]");'''
s=once(s,old,new,'pre-scale static base once')

# Same optimization for the periodic Subscribe master.
old='''  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",&work_fps.to_string(),"-i",job.project.media[0].as_str()].into_iter().map(String::from).collect();\n  for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base=format!("{}[b0]",base_filter(&ws,"0:v"));let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps={fps},format=yuv420p[outv]");'''
new='''  let base_still=work.join("periodic-860-base.png");\n  if !base_still.is_file(){\n    let vf=base_filter(&ws,"0:v");let vf=vf.trim_start_matches("[0:v]").to_string();\n    let prep=vec!["-hide_banner","-loglevel","error","-i",job.project.media[0].as_str(),"-vf",vf.as_str(),"-frames:v","1","-compression_level","1","-y",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n    output(app,"ffmpeg",prep).await.map_err(|e|format!("8.60 periodic static base preprocess: {e}"))?;\n  }\n  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",&work_fps.to_string(),"-i",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n  for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base=format!("[0:v]fps={work_fps},setsar=1[b0]");let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps={fps},format=yuv420p[outv]");'''
s=once(s,old,new,'periodic pre-scale static base once')

# Optimization 2: the seed already contains the only physical video payload and
# all MP3 packets. The old manifest path read it and then rewrote the whole seed
# to a second file. When input==output, rewrite only the trailing moov/sample
# tables in place. The mdat payload is never copied again.
old='''  let mut output=Vec::with_capacity(data.len()+new_moov.len().saturating_sub(moov_ref.size));output.extend_from_slice(&data[..moov_ref.off]);output.extend_from_slice(&new_moov);output.extend_from_slice(&data[moov_ref.off+moov_ref.size..]);fs::write(out,&output).map_err(|e|format!("MP4 manifest: write {}: {e}",out.display()))?;Ok(())'''
new='''  if seed==out{\n    use std::io::{Seek,Write};\n    let tail=data[moov_ref.off+moov_ref.size..].to_vec();\n    let mut f=std::fs::OpenOptions::new().read(true).write(true).open(seed).map_err(|e|format!("MP4 manifest: open in-place {}: {e}",seed.display()))?;\n    f.set_len(moov_ref.off as u64).map_err(|e|format!("MP4 manifest: truncate in-place {}: {e}",seed.display()))?;\n    f.seek(std::io::SeekFrom::Start(moov_ref.off as u64)).map_err(|e|format!("MP4 manifest: seek in-place {}: {e}",seed.display()))?;\n    f.write_all(&new_moov).map_err(|e|format!("MP4 manifest: write moov in-place {}: {e}",seed.display()))?;\n    f.write_all(&tail).map_err(|e|format!("MP4 manifest: write tail in-place {}: {e}",seed.display()))?;\n    f.sync_all().map_err(|e|format!("MP4 manifest: sync in-place {}: {e}",seed.display()))?;\n    Ok(())\n  }else{\n    let mut output=Vec::with_capacity(data.len()+new_moov.len().saturating_sub(moov_ref.size));output.extend_from_slice(&data[..moov_ref.off]);output.extend_from_slice(&new_moov);output.extend_from_slice(&data[moov_ref.off+moov_ref.size..]);fs::write(out,&output).map_err(|e|format!("MP4 manifest: write {}: {e}",out.display()))?;Ok(())\n  }'''
m=once(m,old,new,'in-place moov rewrite')

# Strict Subscribe-OFF and periodic Subscribe-ON both finalize the seed itself,
# then rename it atomically to the requested result. No second 200-500 MB copy.
old='''let manifest=work.join("strict-856-final.mov");let mm=Instant::now();crate::mp4_manifest::expand_video_prefix_cycle(&seed,&manifest,0,master_frames,total_frames)?;std::fs::rename(&manifest,out)'''
new='''let mm=Instant::now();crate::mp4_manifest::expand_video_prefix_cycle(&seed,&seed,0,master_frames,total_frames)?;std::fs::rename(&seed,out)'''
s=once(s,old,new,'strict in-place manifest dispatch')
old='''let manifest=work.join("periodic-852-final.mov");let mark=Instant::now();crate::mp4_manifest::expand_video_prefix_cycle(&seed,&manifest,plan.anchor_frames,plan.repeat_frames,total_frames)?;std::fs::rename(&manifest,out)'''
new='''let mark=Instant::now();crate::mp4_manifest::expand_video_prefix_cycle(&seed,&seed,plan.anchor_frames,plan.repeat_frames,total_frames)?;std::fs::rename(&seed,out)'''
s=once(s,old,new,'periodic in-place manifest dispatch')

R.write_text(s,encoding='utf-8')
M.write_text(m,encoding='utf-8')
print('PASS: ENDLUME 8.60 render-speed stability + in-place manifest migration applied')
