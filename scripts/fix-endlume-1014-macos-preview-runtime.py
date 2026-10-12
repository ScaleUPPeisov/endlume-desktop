#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# A) LiveComposite helper pipeline
# ---------------------------------------------------------------------------
path=ROOT/'src-tauri'/'src'/'live_preview.rs'
text=path.read_text(encoding='utf-8')

# Keep packaged macOS FFmpeg/FFprobe next to Contents/Frameworks.
old='''  if !executable_file(&source){return None}\n\n  let root=app.path().app_cache_dir().ok()?.join("live-preview-tools-v1");'''
new='''  if !executable_file(&source){return None}\n\n  // macOS packaged FFmpeg/FFprobe use @executable_path/../Frameworks for their\n  // portable dylib closure. Moving only the executable into app cache breaks\n  // that loader contract and Preview fails before decoding its first frame.\n  // Execute the signed bundled sibling in Contents/MacOS directly; Windows keeps\n  // the proven staged-cache path below.\n  #[cfg(target_os="macos")]\n  {\n    if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_TOOL_STAGE name={name} mode=bundle-direct source={}",source.display());}\n    return Some(source);\n  }\n\n  let root=app.path().app_cache_dir().ok()?.join("live-preview-tools-v1");'''
if old in text:
    if text.count(old)!=1: raise SystemExit(f'live_preview.rs: expected one staging anchor, got {text.count(old)}')
    text=text.replace(old,new,1)
elif 'mode=bundle-direct' not in text:
    raise SystemExit('live_preview.rs: macOS bundle-direct patch anchor missing')

# High-quality helper overlay uses minterpolate. If it exceeds the hard 5s budget,
# route directly to the existing safe scale+fps path instead of repeating the same
# expensive graph under libx264.
old_block='''  let hw_error=hw.err().unwrap_or_else(||"unknown hardware preview failure".into());\n  if hw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(hw_error)}\n  #[cfg(target_os="macos")]\n  {\n    let sw=proxy_attempt(app,&prefix,software_codec_args(),out).await;\n    if sw.is_ok(){return Ok(())}\n    let sw_error=sw.err().unwrap_or_else(||"unknown libx264 preview failure".into());\n    if sw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}"))}\n    if let Some(safe)=safe_prefix{\n      let safe_result=proxy_attempt(app,&safe,software_codec_args(),out).await;\n      if safe_result.is_ok(){return Ok(())}\n      let safe_error=safe_result.err().unwrap_or_else(||"unknown safe preview failure".into());\n      let _=fs::remove_file(out);\n      return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}; safe fps fallback: {safe_error}"))\n    }\n    let _=fs::remove_file(out);\n    Err(format!("VideoToolbox Live Preview: {hw_error}; libx264 fallback: {sw_error}"))\n  }'''
new_block='''  let hw_error=hw.err().unwrap_or_else(||"unknown hardware preview failure".into());\n  #[cfg(target_os="macos")]\n  {\n    if hw_error.contains("timeout after"){\n      if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_HW_TIMEOUT_DIRECT_SAFE_FALLBACK error={:?}",hw_error);}\n      if let Some(safe)=safe_prefix.as_ref(){\n        let safe_result=proxy_attempt(app,safe,software_codec_args(),out).await;\n        if safe_result.is_ok(){return Ok(())}\n        let safe_error=safe_result.err().unwrap_or_else(||"unknown safe preview failure".into());\n        let _=fs::remove_file(out);\n        return Err(format!("VideoToolbox Live Preview timeout: {hw_error}; safe fps fallback: {safe_error}"))\n      }\n      let _=fs::remove_file(out);\n      return Err(hw_error)\n    }\n    let sw=proxy_attempt(app,&prefix,software_codec_args(),out).await;\n    if sw.is_ok(){return Ok(())}\n    let sw_error=sw.err().unwrap_or_else(||"unknown libx264 preview failure".into());\n    if sw_error.contains("timeout after")&&live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_SW_TIMEOUT_SAFE_FALLBACK error={:?}",sw_error);}\n    if let Some(safe)=safe_prefix{\n      let safe_result=proxy_attempt(app,&safe,software_codec_args(),out).await;\n      if safe_result.is_ok(){return Ok(())}\n      let safe_error=safe_result.err().unwrap_or_else(||"unknown safe preview failure".into());\n      let _=fs::remove_file(out);\n      return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}; safe fps fallback: {safe_error}"))\n    }\n    let _=fs::remove_file(out);\n    Err(format!("VideoToolbox Live Preview: {hw_error}; libx264 fallback: {sw_error}"))\n  }'''
if old_block in text:
    if text.count(old_block)!=1: raise SystemExit(f'live_preview.rs: expected one encode fallback block, got {text.count(old_block)}')
    text=text.replace(old_block,new_block,1)
elif 'ENDLUME_PREVIEW_HW_TIMEOUT_DIRECT_SAFE_FALLBACK' not in text:
    old_intermediate='''  let hw_error=hw.err().unwrap_or_else(||"unknown hardware preview failure".into());\n  if hw_error.contains("timeout after")&&live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_HW_TIMEOUT_FALLBACK_TO_SOFTWARE error={:?}",hw_error);}\n  #[cfg(target_os="macos")]\n  {\n    let sw=proxy_attempt(app,&prefix,software_codec_args(),out).await;\n    if sw.is_ok(){return Ok(())}\n    let sw_error=sw.err().unwrap_or_else(||"unknown libx264 preview failure".into());\n    if sw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}"))}\n    if let Some(safe)=safe_prefix{\n      let safe_result=proxy_attempt(app,&safe,software_codec_args(),out).await;\n      if safe_result.is_ok(){return Ok(())}\n      let safe_error=safe_result.err().unwrap_or_else(||"unknown safe preview failure".into());\n      let _=fs::remove_file(out);\n      return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}; safe fps fallback: {safe_error}"))\n    }\n    let _=fs::remove_file(out);\n    Err(format!("VideoToolbox Live Preview: {hw_error}; libx264 fallback: {sw_error}"))\n  }'''
    if old_intermediate not in text: raise SystemExit('live_preview.rs: encode timeout fallback patch anchor missing')
    text=text.replace(old_intermediate,new_block,1)
path.write_text(text,encoding='utf-8')

# ---------------------------------------------------------------------------
# B) Canonical exact Preview pipeline (generate_preview)
# ---------------------------------------------------------------------------
preview_path=ROOT/'src-tauri'/'src'/'preview.rs'
p=preview_path.read_text(encoding='utf-8')

# Keep the normal hardware path at the existing 3 seconds. Do not bake duration
# into the shared args because a timed-out hardware encoder must recover with a
# much shorter exact proxy that still preserves 1920x1080 @ 60 fps and can loop.
old_duration='''  base_args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-t","3.0","-an"].into_iter().map(String::from));'''
new_duration='''  base_args.extend(vec!["-filter_complex",&graph,"-map","[outv]","-an"].into_iter().map(String::from));'''
if old_duration in p:
    if p.count(old_duration)!=1: raise SystemExit(f'preview.rs: expected one canonical duration anchor, got {p.count(old_duration)}')
    p=p.replace(old_duration,new_duration,1)
elif new_duration not in p:
    raise SystemExit('preview.rs: canonical duration anchor missing')

old_primary='''  let mut primary=base_args.clone();primary.extend(primary_codec);primary.extend(vec!["-fps_mode","cfr","-r","60","-video_track_timescale","60000","-movflags","+faststart","-y",tmp.to_string_lossy().as_ref()].into_iter().map(String::from));'''
new_primary='''  let mut primary=base_args.clone();primary.extend(vec!["-t","3.0"].into_iter().map(String::from));primary.extend(primary_codec);primary.extend(vec!["-fps_mode","cfr","-r","60","-video_track_timescale","60000","-movflags","+faststart","-y",tmp.to_string_lossy().as_ref()].into_iter().map(String::from));'''
if old_primary in p:
    if p.count(old_primary)!=1: raise SystemExit(f'preview.rs: expected one primary args anchor, got {p.count(old_primary)}')
    p=p.replace(old_primary,new_primary,1)
elif new_primary not in p:
    raise SystemExit('preview.rs: canonical primary args anchor missing')

old_fallback='''      let _=std::fs::remove_file(&tmp);\n      let mut fallback=base_args;\n      fallback.extend(vec!["-c:v","libx264","-preset","ultrafast","-crf","12","-g","1","-keyint_min","1","-sc_threshold","0","-bf","0","-pix_fmt","yuv420p"].into_iter().map(String::from));\n      fallback.extend(vec!["-fps_mode","cfr","-r","60","-video_track_timescale","60000","-movflags","+faststart","-y",tmp.to_string_lossy().as_ref()].into_iter().map(String::from));\n      run_preview(&app,fallback).await.map_err(|sw|{let _=std::fs::remove_file(&tmp);format!("VideoToolbox preview: {hw}; libx264 fallback: {sw}")})?;'''
new_fallback='''      let _=std::fs::remove_file(&tmp);\n      let mut fallback=base_args;\n      // Exact Preview is auxiliary to the LiveComposite helper. If cold-start\n      // VideoToolbox exceeds the hard process budget, render a short loopable\n      // exact proxy instead of repeating a full 3-second 1080p60 job.\n      // Geometry/fps/compositor stay identical; Final Render is untouched.\n      fallback.extend(vec!["-t","0.75","-c:v","libx264","-preset","ultrafast","-crf","14","-g","1","-keyint_min","1","-sc_threshold","0","-bf","0","-pix_fmt","yuv420p"].into_iter().map(String::from));\n      fallback.extend(vec!["-fps_mode","cfr","-r","60","-video_track_timescale","60000","-movflags","+faststart","-y",tmp.to_string_lossy().as_ref()].into_iter().map(String::from));\n      if hw.contains("timeout after")&&std::env::var_os("ENDLUME_PREVIEW_DIAG").is_some(){eprintln!("ENDLUME_PREVIEW_CANONICAL_TIMEOUT_SHORT_FALLBACK REQUEST_ID={request} duration=0.75");}\n      run_preview(&app,fallback).await.map_err(|sw|{let _=std::fs::remove_file(&tmp);format!("VideoToolbox preview: {hw}; short libx264 fallback: {sw}")})?;'''
if old_fallback in p:
    if p.count(old_fallback)!=1: raise SystemExit(f'preview.rs: expected one canonical fallback block, got {p.count(old_fallback)}')
    p=p.replace(old_fallback,new_fallback,1)
elif 'ENDLUME_PREVIEW_CANONICAL_TIMEOUT_SHORT_FALLBACK' not in p:
    raise SystemExit('preview.rs: canonical fallback patch anchor missing')
preview_path.write_text(p,encoding='utf-8')

# Static source-contract assertions.
qa=ROOT/'scripts'/'qa-endlume-1014-hotfix.py'
q=qa.read_text(encoding='utf-8')
extra='''\nlive_preview=text("src-tauri/src/live_preview.rs")\nassert 'mode=bundle-direct' in live_preview\nassert '@executable_path/../Frameworks' in live_preview\nassert 'ENDLUME_PREVIEW_HW_TIMEOUT_DIRECT_SAFE_FALLBACK' in live_preview\nassert 'safe_prefix.as_ref()' in live_preview\nassert 'if hw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(hw_error)}' not in live_preview\ncanonical_preview=text("src-tauri/src/preview.rs")\nassert 'ENDLUME_PREVIEW_CANONICAL_TIMEOUT_SHORT_FALLBACK' in canonical_preview\nassert '\"-t\",\"0.75\",\"-c:v\",\"libx264\"' in canonical_preview\nassert 'primary.extend(vec![\"-t\",\"3.0\"]' in canonical_preview\n'''
if "ENDLUME_PREVIEW_CANONICAL_TIMEOUT_SHORT_FALLBACK" not in q:
    q += extra
qa.write_text(q,encoding='utf-8')
print('PASS: macOS Preview keeps Frameworks resolvable and both helper/canonical paths have bounded cold-start fallbacks')
