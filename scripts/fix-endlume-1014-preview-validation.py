#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'src-tauri'/'src'/'live_preview.rs'
text=path.read_text(encoding='utf-8')

# Once FFmpeg has successfully decoded an actual frame, a second FFprobe
# -count_frames pass is redundant and can exceed the same hard 5s cold-start
# budget. Keep metadata validation on the GREEN decode path; retain the deep
# frame-count probe only as an independent fallback when direct decode failed.
metadata_fn='''fn proxy_probe_metadata_valid(raw:&[u8])->bool{\n  let Ok(v)=serde_json::from_slice::<serde_json::Value>(raw) else{return false};\n  let Some(stream)=v.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()) else{return false};\n  if stream.get("codec_type").and_then(|x|x.as_str())!=Some("video"){return false}\n  if !json_positive(stream.get("width"))||!json_positive(stream.get("height")){return false}\n  json_positive(v.get("format").and_then(|x|x.get("duration")))\n}\n'''
if 'fn proxy_probe_metadata_valid' not in text:
    anchor='fn accept_proxy_attempt(process_ok:bool,proxy_valid:bool)->bool{process_ok&&proxy_valid}\n'
    if text.count(anchor)!=1:
        raise SystemExit(f'live_preview.rs: metadata helper anchor count={text.count(anchor)}')
    text=text.replace(anchor,metadata_fn+anchor,1)

old_probe='''  let decode_error=decode_proxy_frame(app,out).await.err();\n  let probe_args=vec![\n    "-v","error","-select_streams","v:0","-count_frames",\n    "-show_entries","stream=codec_type,width,height,nb_read_frames:format=duration",\n    "-of","json",out.to_string_lossy().as_ref()\n  ].into_iter().map(String::from).collect::<Vec<_>>();'''
new_probe='''  let decode_error=decode_proxy_frame(app,out).await.err();\n  let probe_args=if decode_error.is_some(){\n    vec![\n      "-v","error","-select_streams","v:0","-count_frames",\n      "-show_entries","stream=codec_type,width,height,nb_read_frames:format=duration",\n      "-of","json",out.to_string_lossy().as_ref()\n    ]\n  }else{\n    if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_METADATA_ONLY_AFTER_DECODE path={}",out.display());}\n    vec![\n      "-v","error","-select_streams","v:0",\n      "-show_entries","stream=codec_type,width,height:format=duration",\n      "-of","json",out.to_string_lossy().as_ref()\n    ]\n  }.into_iter().map(String::from).collect::<Vec<_>>();'''
if old_probe in text:
    if text.count(old_probe)!=1:
        raise SystemExit(f'live_preview.rs: probe args anchor count={text.count(old_probe)}')
    text=text.replace(old_probe,new_probe,1)
elif 'ENDLUME_PREVIEW_METADATA_ONLY_AFTER_DECODE' not in text:
    raise SystemExit('live_preview.rs: probe args patch anchor missing')

old_validate='''  if !proxy_probe_valid(&probe_stdout){return Err("FFprobe не подтвердил video stream / geometry / decoded frames / duration".into())}\n  if let Some(decode)=decode_error{'''
new_validate='''  let probe_valid=if decode_error.is_some(){proxy_probe_valid(&probe_stdout)}else{proxy_probe_metadata_valid(&probe_stdout)};\n  if !probe_valid{\n    return Err(if decode_error.is_some(){\n      "FFprobe не подтвердил video stream / geometry / decoded frames / duration".into()\n    }else{\n      "FFprobe не подтвердил video stream / geometry / duration после успешного frame decode".into()\n    })\n  }\n  if let Some(decode)=decode_error{'''
if old_validate in text:
    if text.count(old_validate)!=1:
        raise SystemExit(f'live_preview.rs: validation anchor count={text.count(old_validate)}')
    text=text.replace(old_validate,new_validate,1)
elif 'proxy_probe_metadata_valid(&probe_stdout)' not in text:
    raise SystemExit('live_preview.rs: validation patch anchor missing')

path.write_text(text,encoding='utf-8')
print('PASS: Preview validates one real decoded frame once; FFprobe metadata-only on GREEN path, deep recount only on decode fallback')
