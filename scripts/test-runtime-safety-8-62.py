#!/usr/bin/env python3
from pathlib import Path

queue=Path('src-tauri/src/queue.rs').read_text(encoding='utf-8')
render=Path('src-tauri/src/render.rs').read_text(encoding='utf-8')

required_queue=[
  'let active=runtime.active.lock();',
  'let mut q=runtime.pending.lock();',
  'let mut occupied=q.iter().map(|j|j.project.id.clone()).collect::<HashSet<_>>();',
  'if let Some(job)=active.as_ref(){occupied.insert(job.project.id.clone());}',
  'if !occupied.insert(project.id.clone()){continue}',
  'let mut pending=runtime.pending.lock();',
  'if let Some(job)=next.as_ref(){*active=Some(job.clone());}',
]
for needle in required_queue:
  assert needle in queue, f'missing queue duplicate guard: {needle}'

# Source-model regression: active + pending + duplicate incoming must yield one instance per project id.
active='A'
pending=['B','C']
incoming=['A','B','D','D','E']
occupied=set(pending)
occupied.add(active)
accepted=[]
for project_id in incoming:
  if project_id in occupied:
    continue
  occupied.add(project_id)
  accepted.append(project_id)
assert accepted==['D','E'],accepted
assert len(set([active,*pending,*accepted]))==5

required_render=[
  'const LICENSE_BLOCKED:&str="__ENDLUME_LICENSE_BLOCKED__";',
  'fn ensure_license_allowed()->Result<(),String>',
  'ensure_license_allowed()?;crate::mp4_manifest::expand_video_prefix_cycle',
  'verify_strict_857_result(app,&out,final_duration,!processed_audio).await?;}let validation_seconds=verify_mark.elapsed().as_secs_f64();emit_timing(app,&job.project.id,"ffprobe-validation",validation_seconds);emit_timing(app,&job.project.id,"validation",validation_seconds);ensure_license_allowed()?;',
  'if let Err(e)=ensure_license_allowed(){let _=std::fs::remove_dir_all(&work);let _=std::fs::remove_file(&out);return Err(e)}',
  'fn strict_856_validate_natural_size(path:&Path)->Result<(),String>',
]
for needle in required_render:
  assert needle in render, f'missing final revoke/size safety contract: {needle}'

for forbidden in [
  'STRICT_856_PAD_TARGET_BYTES',
  'strict_856_pad_size',
  'f.write_all(b"free")',
  'set_len(current+add)',
]:
  assert forbidden not in render, f'synthetic size padding returned: {forbidden}'

assert render.count('ensure_license_allowed()?') >= 9, render.count('ensure_license_allowed()?')
print('PASS: backend duplicate queue guard + final revoke gate + natural-size/no-padding contract')
