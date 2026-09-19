#!/usr/bin/env python3
from pathlib import Path
import json,sys

ROOT=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
s=(ROOT/'src-tauri/src/render.rs').read_text(encoding='utf-8')
required=[
  'fn render_work_dir(app:&AppHandle,id:&str,attempt:u32)',
  'app.path().app_cache_dir()',
  'let root=base.join("render-work")',
  'fn finalize_local_output(src:&Path,out:&Path)',
  'std::io::copy(&mut input,&mut output)',
  'output.sync_all()',
  'render_work_dir(app,&job.project.id,attempt)',
  'finalize_local_output(&seed,out)',
  'resolved_job.settings.width=1920;',
  'resolved_job.settings.height=1080;',
  'resolved_job.settings.fps=60;',
  '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"',
  'const STRICT_857_MAX_GOP_FRAMES:u32=1800;',
]
for x in required:
    assert x in s, f'missing 8.61 contract: {x}'
assert s.count('finalize_local_output(&seed,out)')==2, s.count('finalize_local_output(&seed,out)')
assert 'let root=output.join(".ENDLUME-work")' not in s
p=json.loads((ROOT/'package.json').read_text())
t=json.loads((ROOT/'src-tauri/tauri.conf.json').read_text())
assert p['version'] in {'1.0.0-alpha.8.61','1.0.0-alpha.8.62','1.0.0-alpha.8.63'}
assert t['version']==p['version']
print('PASS: ENDLUME 8.61+ internal scratch contract preserved under',p['version'])
