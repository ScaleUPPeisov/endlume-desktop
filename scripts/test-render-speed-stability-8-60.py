#!/usr/bin/env python3
from pathlib import Path
import sys

root=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
s=(root/'src-tauri/src/render.rs').read_text(encoding='utf-8')
required=[
  'const STRICT_857_MAX_GOP_FRAMES:u32=1800;',
  'strict-860-base.png',
  'periodic-860-base.png',
  '"-filter_complex_threads","8"',
  '"-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M"',
  'resolved_job.settings.width=1920;',
  'resolved_job.settings.height=1080;',
]
for x in required:
  assert x in s,x
assert 'hevc_videotoolbox' in s
assert 'verify_strict_857_result' in s
print('PASS: ENDLUME 8.60 static-base speed stability anchors')
