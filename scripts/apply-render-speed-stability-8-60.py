#!/usr/bin/env python3
from pathlib import Path
import json,re

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'src-tauri/src/render.rs'
M=ROOT/'src-tauri/src/mp4_manifest.rs'
C=ROOT/'src-tauri/src/cache.rs'
s=R.read_text(encoding='utf-8')
m=M.read_text(encoding='utf-8')
c=C.read_text(encoding='utf-8')

def once(text,old,new,label):
    n=text.count(old)
    if n!=1:
        raise SystemExit(f'8.60 migration: {label}: expected 1 anchor, found {n}')
    return text.replace(old,new,1)

# 8.60 changes only render speed stability and carries the approved 8.59 round
# equalizer chroma profile into the strict cache used by real one-image renders.
# Preserve VideoToolbox q:v100 / GOP1800 / 1920x1080 / CFR60 / MP3 packet copy.
for marker in [
    'const STRICT_857_MAX_GOP_FRAMES:u32=1800;',
    '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"',
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
]:
    if marker not in s: raise SystemExit('8.60 migration: missing invariant '+marker)
if '"-filter_complex_threads","8"' not in s:
    raise SystemExit('8.60 migration: strict 8-thread filter anchor missing')

# Optimization 1: pre-scale/crop the single static still once per job.
old='''  let master=work.join("strict-856-master.mp4");let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-filter_complex_threads","8","-loop","1","-framerate","30","-i",job.project.media[0].as_str()].into_iter().map(String::from).collect();for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base=format!("{}[b0]",base_filter(&ws,"0:v"));let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps=60,format=yuv420p[outv]");'''
new='''  let base_still=work.join("strict-860-base.png");\n  if !base_still.is_file(){\n    let vf=base_filter(&ws,"0:v");\n    let vf=vf.trim_start_matches("[0:v]").to_string();\n    let prep=vec!["-hide_banner","-loglevel","error","-i",job.project.media[0].as_str(),"-vf",vf.as_str(),"-frames:v","1","-compression_level","1","-y",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n    output(app,"ffmpeg",prep).await.map_err(|e|format!("Strict 8.60 static base preprocess: {e}"))?;\n  }\n  let master=work.join("strict-856-master.mp4");let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-filter_complex_threads","8","-loop","1","-framerate","30","-i",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base="[0:v]fps=30,setsar=1[b0]".to_string();let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps=60,format=yuv420p[outv]");'''
s=once(s,old,new,'pre-scale static base once')

# Same optimization for the periodic Subscribe master.
old='''  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",&work_fps.to_string(),"-i",job.project.media[0].as_str()].into_iter().map(String::from).collect();\n  for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base=format!("{}[b0]",base_filter(&ws,"0:v"));let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps={fps},format=yuv420p[outv]");'''
new='''  let base_still=work.join("periodic-860-base.png");\n  if !base_still.is_file(){\n    let vf=base_filter(&ws,"0:v");let vf=vf.trim_start_matches("[0:v]").to_string();\n    let prep=vec!["-hide_banner","-loglevel","error","-i",job.project.media[0].as_str(),"-vf",vf.as_str(),"-frames:v","1","-compression_level","1","-y",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n    output(app,"ffmpeg",prep).await.map_err(|e|format!("8.60 periodic static base preprocess: {e}"))?;\n  }\n  let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error","-loop","1","-framerate",&work_fps.to_string(),"-i",base_still.to_string_lossy().as_ref()].into_iter().map(String::from).collect();\n  for e in effects.iter().filter(|x|x.enabled&&!x.source.trim().is_empty()){args.extend(vec!["-stream_loop","-1","-i",e.source.as_str()].into_iter().map(String::from));}\n  let base=format!("[0:v]fps={work_fps},setsar=1[b0]");let (graph,last)=apply_effects_filter(base,"b0".into(),effects,&ws,1);let graph=format!("{graph};[{last}]fps={fps},format=yuv420p[outv]");'''
s=once(s,old,new,'periodic pre-scale static base once')

# Optimization 2: rewrite only trailing moov/sample tables when input==output.
old='''  let mut output=Vec::with_capacity(data.len()+new_moov.len().saturating_sub(moov_ref.size));output.extend_from_slice(&data[..moov_ref.off]);output.extend_from_slice(&new_moov);output.extend_from_slice(&data[moov_ref.off+moov_ref.size..]);fs::write(out,&output).map_err(|e|format!("MP4 manifest: write {}: {e}",out.display()))?;Ok(())'''
new='''  if seed==out{\n    use std::io::{Seek,Write};\n    let tail=data[moov_ref.off+moov_ref.size..].to_vec();\n    let mut f=std::fs::OpenOptions::new().read(true).write(true).open(seed).map_err(|e|format!("MP4 manifest: open in-place {}: {e}",seed.display()))?;\n    f.set_len(moov_ref.off as u64).map_err(|e|format!("MP4 manifest: truncate in-place {}: {e}",seed.display()))?;\n    f.seek(std::io::SeekFrom::Start(moov_ref.off as u64)).map_err(|e|format!("MP4 manifest: seek in-place {}: {e}",seed.display()))?;\n    f.write_all(&new_moov).map_err(|e|format!("MP4 manifest: write moov in-place {}: {e}",seed.display()))?;\n    f.write_all(&tail).map_err(|e|format!("MP4 manifest: write tail in-place {}: {e}",seed.display()))?;\n    f.sync_all().map_err(|e|format!("MP4 manifest: sync in-place {}: {e}",seed.display()))?;\n    Ok(())\n  }else{\n    let mut output=Vec::with_capacity(data.len()+new_moov.len().saturating_sub(moov_ref.size));output.extend_from_slice(&data[..moov_ref.off]);output.extend_from_slice(&new_moov);output.extend_from_slice(&data[moov_ref.off+moov_ref.size..]);fs::write(out,&output).map_err(|e|format!("MP4 manifest: write {}: {e}",out.display()))?;Ok(())\n  }'''
m=once(m,old,new,'in-place moov rewrite')
old='''let manifest=work.join("strict-856-final.mov");let mm=Instant::now();crate::mp4_manifest::expand_video_prefix_cycle(&seed,&manifest,0,master_frames,total_frames)?;std::fs::rename(&manifest,out)'''
new='''let mm=Instant::now();crate::mp4_manifest::expand_video_prefix_cycle(&seed,&seed,0,master_frames,total_frames)?;std::fs::rename(&seed,out)'''
s=once(s,old,new,'strict in-place manifest dispatch')
old='''let manifest=work.join("periodic-852-final.mov");let mark=Instant::now();crate::mp4_manifest::expand_video_prefix_cycle(&seed,&manifest,plan.anchor_frames,plan.repeat_frames,total_frames)?;std::fs::rename(&manifest,out)'''
new='''let mark=Instant::now();crate::mp4_manifest::expand_video_prefix_cycle(&seed,&seed,plan.anchor_frames,plan.repeat_frames,total_frames)?;std::fs::rename(&seed,out)'''
s=once(s,old,new,'periodic in-place manifest dispatch')
R.write_text(s,encoding='utf-8')
M.write_text(m,encoding='utf-8')

# Carry the approved 8.59 round equalizer profile into Strict Effects cache.
if 'fn chromakey_params_859' not in c:
    raise SystemExit('8.60 migration: 8.59 protected equalizer helper missing')
old='''  let mut h=Sha256::new();h.update(format!("strict-856|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",e.source,size,modified,fps,width,height,e.mode,e.key_color,e.similarity,e.blend,e.luma_threshold,e.luma_tolerance,e.scale,e.fullscreen,e.saturation));hex::encode(h.finalize())[..24].to_string()'''
new='''  let (similarity,blend)=chromakey_params_859(e);let mut h=Sha256::new();h.update(format!("strict-860|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",e.source,size,modified,fps,width,height,e.mode,e.key_color,similarity,blend,e.luma_threshold,e.luma_tolerance,e.scale,e.fullscreen,e.saturation));hex::encode(h.finalize())[..24].to_string()'''
c=once(c,old,new,'strict cache fingerprint protected chroma')
old='''        let target=((width as f64)*e.scale.clamp(0.05,1.5)).round().max(2.0) as u32;let target=if target%2==0{target}else{target+1};\n        let scale=if e.fullscreen{format!("scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0")}else{format!("scale={target}:-2:flags=lanczos")};\n        let vf=match e.mode.as_str(){'''
new='''        let target=((width as f64)*e.scale.clamp(0.05,1.5)).round().max(2.0) as u32;let target=if target%2==0{target}else{target+1};\n        let scale=if e.fullscreen{format!("scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0")}else{format!("scale={target}:-2:flags=lanczos")};\n        let (similarity,blend)=chromakey_params_859(e);\n        let vf=match e.mode.as_str(){'''
c=once(c,old,new,'strict cache protected chroma locals')
old='''          _=>format!("fps={fps},format=rgba,colorkey={}:{}:{},{scale},format=argb",color(&e.key_color),e.similarity.clamp(0.001,0.60),e.blend.clamp(0.001,0.35))'''
new='''          _=>format!("fps={fps},format=rgba,colorkey={}:{}:{},{scale},format=argb",color(&e.key_color),similarity,blend)'''
c=once(c,old,new,'strict cache protected chroma vf')
C.write_text(c,encoding='utf-8')

# Final visible/package identity after the effective 8.58 migration.
for rel in ['package.json','src-tauri/tauri.conf.json']:
    p=ROOT/rel; d=json.loads(p.read_text()); d['version']='1.0.0-alpha.8.60'; p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'src-tauri/Cargo.toml'; txt=p.read_text(); txt,n=re.subn(r'(?m)^version\s*=\s*"1\.0\.0-alpha\.8\.58"$', 'version = "1.0.0-alpha.8.60"',txt,count=1)
if n!=1: raise SystemExit('8.60 migration: Cargo 8.58 version anchor missing')
p.write_text(txt)
p=ROOT/'package-lock.json'
if p.exists():
    d=json.loads(p.read_text()); d['version']='1.0.0-alpha.8.60'
    if isinstance(d.get('packages'),dict) and '' in d['packages']: d['packages']['']['version']='1.0.0-alpha.8.60'
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
P=ROOT/'src/pages/SettingsPage.tsx'; ui=P.read_text()
if '1.0.0-alpha.8.58' not in ui: raise SystemExit('8.60 migration: Settings 8.58 anchor missing')
P.write_text(ui.replace('1.0.0-alpha.8.58','1.0.0-alpha.8.60'))
H=ROOT/'src/components/ReleaseHistory.tsx'; h=H.read_text()
old="version:'1.0.0-alpha.8.58',date:'06.09.2026',current:true"
if old not in h: raise SystemExit('8.60 migration: ReleaseHistory 8.58 current anchor missing')
h=h.replace(old,"version:'1.0.0-alpha.8.58',date:'06.09.2026',current:false",1)
anchor='const releases:Release[]=[\n'
entry="""const releases:Release[]=[
  {version:'1.0.0-alpha.8.60',date:'07.09.2026',current:true,title:'Render Speed Stability • Equalizer Carry-Forward',items:[
    'Статичная картинка 1920×1080 масштабируется/crop один раз на проект вместо повторной обработки каждого кадра strict master.',
    'Физический gate проверяет 5 последовательных реальных master подряд с пределом 30 секунд на каждый, чтобы не возвращался рост времени очереди.',
    'Zero-copy manifest обновляет sample tables in-place без повторной полной перезаписи большого MOV.',
    'Круглый эквалайзер использует защищённый chromakey 0.18 / 0.03 и в Strict Effects cache, поэтому не становится тусклым в реальном рендере.',
    'Сохранены HEVC VideoToolbox q:v100, GOP1800, 1920×1080 CFR60, untouched MP3, whole-song, Effects/Subscribe, 500–700 МБ, VYRON и queue contracts.'
  ]},
"""
if anchor not in h: raise SystemExit('8.60 migration: ReleaseHistory list anchor missing')
H.write_text(h.replace(anchor,entry,1))

print('PASS: ENDLUME 8.60 speed stability + in-place manifest + strict equalizer + version contracts applied')
