#!/usr/bin/env python3
from pathlib import Path
import json,re,sys

root=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
s=(root/'src-tauri/src/render.rs').read_text(encoding='utf-8')
c=(root/'src-tauri/src/cache.rs').read_text(encoding='utf-8')
required=[
  'const STRICT_857_MAX_GOP_FRAMES:u32=1800;',
  'strict-860-base.png',
  'periodic-860-base.png',
  '"-filter_complex_threads","8"',
  '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"',
  'resolved_job.settings.width=1920;',
  'resolved_job.settings.height=1080;',
  'expand_video_prefix_cycle(&seed,&seed,0,master_frames,total_frames)',
  'expand_video_prefix_cycle(&seed,&seed,plan.anchor_frames,plan.repeat_frames,total_frames)',
]
for x in required: assert x in s,x
for x in ['hevc_videotoolbox','verify_strict_857_result']: assert x in s,x
for x in ['fn chromakey_params_859','strict-860|','let (similarity,blend)=chromakey_params_859(e);','color(&e.key_color),similarity,blend']:
  assert x in c,x
pkg=json.load(open(root/'package.json'))['version']
tauri=json.load(open(root/'src-tauri/tauri.conf.json'))['version']
assert pkg in {'1.0.0-alpha.8.60','1.0.0-alpha.8.61','1.0.0-alpha.8.62','1.0.0-alpha.8.63'},pkg
assert tauri==pkg,(tauri,pkg)
ct=(root/'src-tauri/Cargo.toml').read_text();assert re.search(r'^version\s*=\s*"'+re.escape(pkg)+r'"$',ct,re.M),pkg
assert pkg in (root/'src/pages/SettingsPage.tsx').read_text()
h=(root/'src/components/ReleaseHistory.tsx').read_text();assert "version:'1.0.0-alpha.8.60'" in h
if pkg.endswith(('8.61','8.62','8.63')): assert f"version:'{pkg}'" in h
print('PASS: ENDLUME 8.60 render-speed/equalizer/in-place-manifest contracts preserved under',pkg)
