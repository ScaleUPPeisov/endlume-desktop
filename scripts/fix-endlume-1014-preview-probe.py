#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'src-tauri'/'src'/'live_preview.rs'
text=path.read_text(encoding='utf-8')

# validate_video_proxy already performs a real first-frame FFmpeg decode before
# FFprobe. On the normal GREEN path, running FFprobe -count_frames immediately
# afterwards decodes the whole proxy a second time and can exceed the same hard
# 5-second cold-start budget. Use a metadata-only probe after a successful real
# decode; retain count_frames as the independent fallback only when decode failed.

old_probe_fn='''fn proxy_probe_valid(raw:&[u8])->bool{\n  let Ok(v)=serde_json::from_slice::<serde_json::Value>(raw) else{return false};\n  let Some(stream)=v.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()) else{return false};\n  if stream.get("codec_type").and_then(|x|x.as_str())!=Some("video"){return false}\n  if !json_positive(stream.get("width"))||!json_positive(stream.get("height")){return false}\n  if !json_positive(stream.get("nb_read_frames")){return false}\n  json_positive(v.get("format").and_then(|x|x.get("duration")))\n}\n'''
new_probe_fn=old_probe_fn+'''fn proxy_probe_metadata_valid(raw:&[u8])->bool{\n  let Ok(v)=serde_json::from_slice::<serde_json::Value>(raw) else{return false};\n  let Some(stream)=v.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()) else{return false};\n  if stream.get("codec_type").and_then(|x|x.as_str())!=Some("video"){return false}\n  if !json_positive(stream.get("width"))||!json_positive(stream.get("height")){return false}\n  json_positive(v.get("format").and_then(|x|x.get("duration")))\n}\n'''
if 'fn proxy_probe_metadata_valid' not in text:
    if text.count(old_probe_fn)!=1:
        raise SystemExit(f'live_preview.rs: proxy_probe_valid shape mismatch: {text.count(old_probe_fn)}')
    text=text.replace(old_probe_fn,new_probe_fn,1)

old_args='''  let decode_error=decode_proxy_frame(app,out).await.err();\n  let probe_args=vec![\n    "-v","error","-select_streams","v:0","-count_frames",\n    "-show_entries","stream=codec_type,width,height,nb_read_frames:format=duration",\n    "-of","json",out.to_string_lossy().as_ref()\n  ].into_iter().map(String::from).collect::<Vec<_>>();'''
new_args='''  let decode_error=decode_proxy_frame(app,out).await.err();\n  let deep_probe=decode_error.is_some();\n  let out_arg=out.to_string_lossy().into_owned();\n  let probe_args=if deep_probe{\n    vec![\n      "-v".into(),"error".into(),"-select_streams".into(),"v:0".into(),"-count_frames".into(),\n      "-show_entries".into(),"stream=codec_type,width,height,nb_read_frames:format=duration".into(),\n      "-of".into(),"json".into(),out_arg.clone()\n    ]\n  }else{\n    vec![\n      "-v".into(),"error".into(),"-select_streams".into(),"v:0".into(),\n      "-show_entries".into(),"stream=codec_type,width,height:format=duration".into(),\n      "-of".into(),"json".into(),out_arg\n    ]\n  };\n  if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_PROBE_MODE={} path={}",if deep_probe{"count-frames-fallback"}else{"metadata-after-real-decode"},out.display());}'''
if old_args in text:
    if text.count(old_args)!=1:
        raise SystemExit(f'live_preview.rs: probe args shape mismatch: {text.count(old_args)}')
    text=text.replace(old_args,new_args,1)
elif 'ENDLUME_PREVIEW_PROBE_MODE=' not in text:
    raise SystemExit('live_preview.rs: validate_video_proxy probe args anchor missing')

old_validation='''  if !probe_success{return Err(format!("FFprobe не принял proxy: {}",String::from_utf8_lossy(&probe_stderr).trim()))}\n  if !proxy_probe_valid(&probe_stdout){return Err("FFprobe не подтвердил video stream / geometry / decoded frames / duration".into())}\n  if let Some(decode)=decode_error{'''
new_validation='''  if !probe_success{return Err(format!("FFprobe не принял proxy: {}",String::from_utf8_lossy(&probe_stderr).trim()))}\n  let probe_valid=if deep_probe{proxy_probe_valid(&probe_stdout)}else{proxy_probe_metadata_valid(&probe_stdout)};\n  if !probe_valid{return Err(if deep_probe{"FFprobe не подтвердил video stream / geometry / decoded frames / duration".into()}else{"FFprobe не подтвердил video stream / geometry / duration после реального decode".into()})}\n  if let Some(decode)=decode_error{'''
if old_validation in text:
    if text.count(old_validation)!=1:
        raise SystemExit(f'live_preview.rs: probe validation shape mismatch: {text.count(old_validation)}')
    text=text.replace(old_validation,new_validation,1)
elif 'let probe_valid=if deep_probe' not in text:
    raise SystemExit('live_preview.rs: probe validation anchor missing')

path.write_text(text,encoding='utf-8')

qa=ROOT/'scripts'/'qa-endlume-1014-hotfix.py'
q=qa.read_text(encoding='utf-8')
extra='''\nlive_preview_probe=text("src-tauri/src/live_preview.rs")\nassert 'fn proxy_probe_metadata_valid' in live_preview_probe\nassert 'ENDLUME_PREVIEW_PROBE_MODE=' in live_preview_probe\nassert 'let deep_probe=decode_error.is_some()' in live_preview_probe\nassert 'let out_arg=out.to_string_lossy().into_owned()' in live_preview_probe\nassert 'let probe_valid=if deep_probe' in live_preview_probe\n'''
if 'ENDLUME_PREVIEW_PROBE_MODE=' not in q:
    q += extra
elif 'let out_arg=out.to_string_lossy().into_owned()' not in q:
    q += '''\nlive_preview_probe=text("src-tauri/src/live_preview.rs")\nassert 'let out_arg=out.to_string_lossy().into_owned()' in live_preview_probe\n'''
qa.write_text(q,encoding='utf-8')
print('PASS: successful real Preview decode uses bounded metadata FFprobe; count_frames remains decode-error fallback only; probe path is owned')
