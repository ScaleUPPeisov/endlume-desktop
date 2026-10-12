#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'src-tauri'/'src'/'live_preview.rs'
text=path.read_text(encoding='utf-8')

old='''  if !executable_file(&source){return None}\n\n  let root=app.path().app_cache_dir().ok()?.join("live-preview-tools-v1");'''
new='''  if !executable_file(&source){return None}\n\n  // macOS packaged FFmpeg/FFprobe use @executable_path/../Frameworks for their\n  // portable dylib closure. Moving only the executable into app cache breaks\n  // that loader contract and Preview fails before decoding its first frame.\n  // Execute the signed bundled sibling in Contents/MacOS directly; Windows keeps\n  // the proven staged-cache path below.\n  #[cfg(target_os="macos")]\n  {\n    if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_TOOL_STAGE name={name} mode=bundle-direct source={}",source.display());}\n    return Some(source);\n  }\n\n  let root=app.path().app_cache_dir().ok()?.join("live-preview-tools-v1");'''
if old in text:
    if text.count(old)!=1:
        raise SystemExit(f'live_preview.rs: expected one staging anchor, got {text.count(old)}')
    text=text.replace(old,new,1)
elif 'mode=bundle-direct' not in text:
    raise SystemExit('live_preview.rs: macOS bundle-direct patch anchor missing')
path.write_text(text,encoding='utf-8')

qa=ROOT/'scripts'/'qa-endlume-1014-hotfix.py'
q=qa.read_text(encoding='utf-8')
extra='''\nlive_preview=text("src-tauri/src/live_preview.rs")\nassert 'mode=bundle-direct' in live_preview\nassert '@executable_path/../Frameworks' in live_preview\n'''
if "assert 'mode=bundle-direct' in live_preview" not in q:
    q += extra
qa.write_text(q,encoding='utf-8')
print('PASS: macOS Preview tools stay in app bundle so Frameworks remain resolvable')
