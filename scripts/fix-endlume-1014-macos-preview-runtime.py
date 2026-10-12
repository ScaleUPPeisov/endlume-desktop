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

# 2) A bounded VideoToolbox timeout is not a terminal Preview failure.
# The proven software encoder is the recovery path. Keep each subprocess bounded
# by PREVIEW_PROCESS_TIMEOUT and only stop after the software attempt also times out.
old_timeout='''  if hw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(hw_error)}\n  #[cfg(target_os="macos")]'''
new_timeout='''  if hw_error.contains("timeout after")&&live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_HW_TIMEOUT_FALLBACK_TO_SOFTWARE error={:?}",hw_error);}\n  #[cfg(target_os="macos")]'''
if old_timeout in text:
    if text.count(old_timeout)!=1:
        raise SystemExit(f'live_preview.rs: expected one hardware timeout terminal guard, got {text.count(old_timeout)}')
    text=text.replace(old_timeout,new_timeout,1)
elif 'ENDLUME_PREVIEW_HW_TIMEOUT_FALLBACK_TO_SOFTWARE' not in text:
    raise SystemExit('live_preview.rs: hardware-timeout fallback patch anchor missing')

path.write_text(text,encoding='utf-8')

qa=ROOT/'scripts'/'qa-endlume-1014-hotfix.py'
q=qa.read_text(encoding='utf-8')
extra='''\nlive_preview=text("src-tauri/src/live_preview.rs")\nassert 'mode=bundle-direct' in live_preview\nassert '@executable_path/../Frameworks' in live_preview\nassert 'ENDLUME_PREVIEW_HW_TIMEOUT_FALLBACK_TO_SOFTWARE' in live_preview\nassert 'if hw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(hw_error)}' not in live_preview\n'''
if "assert 'mode=bundle-direct' in live_preview" not in q:
    q += extra
elif "ENDLUME_PREVIEW_HW_TIMEOUT_FALLBACK_TO_SOFTWARE" not in q:
    q += '''\nlive_preview=text("src-tauri/src/live_preview.rs")\nassert 'ENDLUME_PREVIEW_HW_TIMEOUT_FALLBACK_TO_SOFTWARE' in live_preview\nassert 'if hw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(hw_error)}' not in live_preview\n'''
qa.write_text(q,encoding='utf-8')
print('PASS: macOS Preview keeps Frameworks resolvable and falls back from bounded VideoToolbox timeout to software')
