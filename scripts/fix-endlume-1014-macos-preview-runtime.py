#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'src-tauri'/'src'/'live_preview.rs'
text=path.read_text(encoding='utf-8')

# 1) Keep packaged macOS FFmpeg/FFprobe next to Contents/Frameworks.
old='''  if !executable_file(&source){return None}\n\n  let root=app.path().app_cache_dir().ok()?.join("live-preview-tools-v1");'''
new='''  if !executable_file(&source){return None}\n\n  // macOS packaged FFmpeg/FFprobe use @executable_path/../Frameworks for their\n  // portable dylib closure. Moving only the executable into app cache breaks\n  // that loader contract and Preview fails before decoding its first frame.\n  // Execute the signed bundled sibling in Contents/MacOS directly; Windows keeps\n  // the proven staged-cache path below.\n  #[cfg(target_os="macos")]\n  {\n    if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_TOOL_STAGE name={name} mode=bundle-direct source={}",source.display());}\n    return Some(source);\n  }\n\n  let root=app.path().app_cache_dir().ok()?.join("live-preview-tools-v1");'''
if old in text:
    if text.count(old)!=1:
        raise SystemExit(f'live_preview.rs: expected one staging anchor, got {text.count(old)}')
    text=text.replace(old,new,1)
elif 'mode=bundle-direct' not in text:
    raise SystemExit('live_preview.rs: macOS bundle-direct patch anchor missing')

# 2) The high-quality overlay prefix uses minterpolate and can legitimately exceed
# the 5s cold-process budget. A timeout must not launch the exact same expensive
# filter again under libx264. Route it directly to the already-proven safe prefix
# (scale + fps=60) and keep every subprocess hard-bounded by PREVIEW_PROCESS_TIMEOUT.
old_block='''  let hw_error=hw.err().unwrap_or_else(||"unknown hardware preview failure".into());\n  if hw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(hw_error)}\n  #[cfg(target_os="macos")]\n  {\n    let sw=proxy_attempt(app,&prefix,software_codec_args(),out).await;\n    if sw.is_ok(){return Ok(())}\n    let sw_error=sw.err().unwrap_or_else(||"unknown libx264 preview failure".into());\n    if sw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}"))}\n    if let Some(safe)=safe_prefix{\n      let safe_result=proxy_attempt(app,&safe,software_codec_args(),out).await;\n      if safe_result.is_ok(){return Ok(())}\n      let safe_error=safe_result.err().unwrap_or_else(||"unknown safe preview failure".into());\n      let _=fs::remove_file(out);\n      return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}; safe fps fallback: {safe_error}"))\n    }\n    let _=fs::remove_file(out);\n    Err(format!("VideoToolbox Live Preview: {hw_error}; libx264 fallback: {sw_error}"))\n  }'''
new_block='''  let hw_error=hw.err().unwrap_or_else(||"unknown hardware preview failure".into());\n  #[cfg(target_os="macos")]\n  {\n    if hw_error.contains("timeout after"){\n      if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_HW_TIMEOUT_DIRECT_SAFE_FALLBACK error={:?}",hw_error);}\n      if let Some(safe)=safe_prefix.as_ref(){\n        let safe_result=proxy_attempt(app,safe,software_codec_args(),out).await;\n        if safe_result.is_ok(){return Ok(())}\n        let safe_error=safe_result.err().unwrap_or_else(||"unknown safe preview failure".into());\n        let _=fs::remove_file(out);\n        return Err(format!("VideoToolbox Live Preview timeout: {hw_error}; safe fps fallback: {safe_error}"))\n      }\n      let _=fs::remove_file(out);\n      return Err(hw_error)\n    }\n    let sw=proxy_attempt(app,&prefix,software_codec_args(),out).await;\n    if sw.is_ok(){return Ok(())}\n    let sw_error=sw.err().unwrap_or_else(||"unknown libx264 preview failure".into());\n    if sw_error.contains("timeout after")&&live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_SW_TIMEOUT_SAFE_FALLBACK error={:?}",sw_error);}\n    if let Some(safe)=safe_prefix{\n      let safe_result=proxy_attempt(app,&safe,software_codec_args(),out).await;\n      if safe_result.is_ok(){return Ok(())}\n      let safe_error=safe_result.err().unwrap_or_else(||"unknown safe preview failure".into());\n      let _=fs::remove_file(out);\n      return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}; safe fps fallback: {safe_error}"))\n    }\n    let _=fs::remove_file(out);\n    Err(format!("VideoToolbox Live Preview: {hw_error}; libx264 fallback: {sw_error}"))\n  }'''
if old_block in text:
    if text.count(old_block)!=1:
        raise SystemExit(f'live_preview.rs: expected one encode fallback block, got {text.count(old_block)}')
    text=text.replace(old_block,new_block,1)
elif 'ENDLUME_PREVIEW_HW_TIMEOUT_DIRECT_SAFE_FALLBACK' not in text:
    # Support the intermediate candidate where hardware timeout already continued
    # to the expensive software prefix.
    old_intermediate='''  let hw_error=hw.err().unwrap_or_else(||"unknown hardware preview failure".into());\n  if hw_error.contains("timeout after")&&live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_HW_TIMEOUT_FALLBACK_TO_SOFTWARE error={:?}",hw_error);}\n  #[cfg(target_os="macos")]\n  {\n    let sw=proxy_attempt(app,&prefix,software_codec_args(),out).await;\n    if sw.is_ok(){return Ok(())}\n    let sw_error=sw.err().unwrap_or_else(||"unknown libx264 preview failure".into());\n    if sw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}"))}\n    if let Some(safe)=safe_prefix{\n      let safe_result=proxy_attempt(app,&safe,software_codec_args(),out).await;\n      if safe_result.is_ok(){return Ok(())}\n      let safe_error=safe_result.err().unwrap_or_else(||"unknown safe preview failure".into());\n      let _=fs::remove_file(out);\n      return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}; safe fps fallback: {safe_error}"))\n    }\n    let _=fs::remove_file(out);\n    Err(format!("VideoToolbox Live Preview: {hw_error}; libx264 fallback: {sw_error}"))\n  }'''
    if old_intermediate not in text:
        raise SystemExit('live_preview.rs: encode timeout fallback patch anchor missing')
    text=text.replace(old_intermediate,new_block,1)

path.write_text(text,encoding='utf-8')

qa=ROOT/'scripts'/'qa-endlume-1014-hotfix.py'
q=qa.read_text(encoding='utf-8')
extra='''\nlive_preview=text("src-tauri/src/live_preview.rs")\nassert 'mode=bundle-direct' in live_preview\nassert '@executable_path/../Frameworks' in live_preview\nassert 'ENDLUME_PREVIEW_HW_TIMEOUT_DIRECT_SAFE_FALLBACK' in live_preview\nassert 'safe_prefix.as_ref()' in live_preview\nassert 'if hw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(hw_error)}' not in live_preview\n'''
if "ENDLUME_PREVIEW_HW_TIMEOUT_DIRECT_SAFE_FALLBACK" not in q:
    q += extra
qa.write_text(q,encoding='utf-8')
print('PASS: macOS Preview keeps Frameworks resolvable and routes bounded high-quality timeout directly to safe software proxy')
