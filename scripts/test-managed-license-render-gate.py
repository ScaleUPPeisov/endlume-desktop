#!/usr/bin/env python3
from pathlib import Path
s=Path('src-tauri/src/render.rs').read_text()
checks=[
 ('ffmpeg remote cancel','if crate::license::production_blocked(){if let Some(c)=child.take(){let _=c.kill();}return Err("__ENDLUME_LICENSE_BLOCKED__".into())}'),
 ('render entry gate','pub async fn render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<(),String>{\n  if crate::license::production_blocked(){return Err("__ENDLUME_LICENSE_BLOCKED__".into())}'),
 ('live telemetry','crate::license::telemetry_render_progress(job,progress.clamp(0.0,99.9),eta,stage,encoder);'),
]
for name,needle in checks:
    if needle not in s: raise SystemExit(f'FAIL {name}')
print('ENDLUME_MANAGED_LICENSE_RENDER_GATE_GREEN')
