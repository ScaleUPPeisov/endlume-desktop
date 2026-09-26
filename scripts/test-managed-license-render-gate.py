#!/usr/bin/env python3
from pathlib import Path
s=Path('src-tauri/src/render.rs').read_text()
checks=[
 ('license blocked constant','const LICENSE_BLOCKED:&str="__ENDLUME_LICENSE_BLOCKED__";'),
 ('ffmpeg remote cancel','if crate::license::production_blocked(){if let Some(c)=child.take(){let _=c.kill();}return Err(LICENSE_BLOCKED.into())}'),
 ('render entry gate','pub async fn render_job(app:&AppHandle,job:&QueueJob,cancel:Arc<AtomicBool>)->Result<RenderOutcome,String>{\n  ensure_license_allowed()?;'),
 ('zero-copy pre/post gate','ensure_license_allowed()?;crate::mp4_manifest::expand_video_prefix_cycle'),
 ('multi-still manifest gate','ensure_license_allowed()?;crate::mp4_manifest::remap_video_samples(&seed,&seed,&selected)?;ensure_license_allowed()?;'),
 ('final verify gate','verify_strict_857_result(app,&out,final_duration,!processed_audio).await?;}let validation_seconds=verify_mark.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"ffprobe-validation",validation_seconds);emit_timing(app,&job.project.id,"validation",validation_seconds);ensure_license_allowed()?;'),
 ('final success gate','if let Err(e)=ensure_license_allowed(){let _=std::fs::remove_dir_all(&work);let _=std::fs::remove_file(&out);return Err(e)}'),
 ('live telemetry','crate::license::telemetry_render_progress(job,progress.clamp(0.0,99.9),eta,stage,encoder);'),
]
for name,needle in checks:
    if needle not in s: raise SystemExit(f'FAIL {name}')
if s.count('ensure_license_allowed()?') < 9:
    raise SystemExit(f'FAIL final license gates count={s.count("ensure_license_allowed()?")}')
print('ENDLUME_MANAGED_LICENSE_RENDER_GATE_GREEN')
