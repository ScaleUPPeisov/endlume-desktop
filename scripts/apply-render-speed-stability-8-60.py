#!/usr/bin/env python3
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'src-tauri/src/render.rs'
s=R.read_text(encoding='utf-8')

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

# The physical sustained benchmark proved 8 filter threads are still the fastest
# on the M1. Keep them pinned instead of trying to reduce parallelism.
if '"-filter_complex_threads","8"' not in s:
    raise SystemExit('8.60 migration: strict 8-thread filter anchor missing')

# Optimization 1: pre-scale/crop the static still once per render job and feed
# the strict master from that preprocessed frame. The old path ran Lanczos scale
# and crop for every one of the 3381 master frames, which amplifies warm-run cost.
old='''  let master=work.join("strict-856-master.mp4");let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-filter_complex_threads","8","-loop","1","-framerate","30","-i",job.project.media[0].as_str()].into_iter().map(String::from).collect();for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base=format!("{}[b0]",base_filter(&ws,"0:v"));let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps=60,format=yuv420p[outv]");'''
new='''  let base_still=work.join("strict-860-base.png");\n  if !base_still.is_file(){\n    let vf=base_filter(&ws,"0:v");\n    let vf=vf.trim_end_matches("[b0]").to_string();\n    let prep=vec!["-hide_banner","-loglevel","error","-i",job.project.media[0].as_str(),"-vf",vf.as_str(),"-frames:v","1","-compression_level","1","-y",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n    output(app,"ffmpeg",prep).await.map_err(|e|format!("Strict 8.60 static base preprocess: {e}"))?;\n  }\n  let master=work.join("strict-856-master.mp4");let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-filter_complex_threads","8","-loop","1","-framerate","30","-i",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base="[0:v]fps=30,setsar=1[b0]".to_string();let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps=60,format=yuv420p[outv]");'''
s=once(s,old,new,'pre-scale static base once')

# Apply the same one-frame preprocessing to the periodic Subscribe master so the
# Subscribe-ON path cannot regress while OFF is accelerated.
old='''  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",&work_fps.to_string(),"-i",job.project.media[0].as_str()].into_iter().map(String::from).collect();\n  for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base=format!("{}[b0]",base_filter(&ws,"0:v"));let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps={fps},format=yuv420p[outv]");'''
new='''  let base_still=work.join("periodic-860-base.png");\n  if !base_still.is_file(){\n    let vf=base_filter(&ws,"0:v");let vf=vf.trim_end_matches("[b0]").to_string();\n    let prep=vec!["-hide_banner","-loglevel","error","-i",job.project.media[0].as_str(),"-vf",vf.as_str(),"-frames:v","1","-compression_level","1","-y",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n    output(app,"ffmpeg",prep).await.map_err(|e|format!("8.60 periodic static base preprocess: {e}"))?;\n  }\n  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",&work_fps.to_string(),"-i",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n  for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base=format!("[0:v]fps={work_fps},setsar=1[b0]");let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps={fps},format=yuv420p[outv]");'''
s=once(s,old,new,'periodic pre-scale static base once')

R.write_text(s,encoding='utf-8')
print('PASS: ENDLUME 8.60 render-speed stability migration applied')
