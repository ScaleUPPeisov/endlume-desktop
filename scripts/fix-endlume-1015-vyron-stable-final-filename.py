#!/usr/bin/env python3
from pathlib import Path

RENDER = Path('src-tauri/src/render.rs')
FAST = Path('src-tauri/src/fast_render.rs')

render = RENDER.read_text(encoding='utf-8')
fast = FAST.read_text(encoding='utf-8')

marker = 'ENDLUME_VYRON_STABLE_FINAL_FILENAME'
if marker not in render:
    anchor = '''fn unique_output(dir:&Path,name:&str)->PathBuf{let safe=safe_name(name);let mut p=dir.join(format!("{} — Ready Videos.mp4",safe));let mut n=2;while p.exists(){p=dir.join(format!("{} — Ready Videos_{}.mp4",safe,n));n+=1}p}\n'''
    if anchor not in render:
        raise SystemExit('render.rs unique_output anchor missing')
    helper = '''// ENDLUME_VYRON_STABLE_FINAL_FILENAME\n// A VYRON project represents one production job with one canonical final media\n// path. Re-running the same job (including after app restart) must replace that\n// final media instead of silently creating Ready Videos_2/_3 duplicates.\n// Standalone ENDLUME keeps the historical unique-output behavior.\npub(crate) fn final_output_path(job:&QueueJob,dir:&Path)->PathBuf{\n  let vyron=job.project.output_source.as_deref().map(str::trim).map(|s|s.eq_ignore_ascii_case("vyron")).unwrap_or(false)\n    ||job.project.vyron_manifest_path.as_deref().map(str::trim).map(|s|!s.is_empty()).unwrap_or(false)\n    ||job.project.vyron_channel_name.as_deref().map(str::trim).map(|s|!s.is_empty()).unwrap_or(false);\n  if vyron{dir.join(format!("{} — Ready Videos.mp4",safe_name(&job.project.name)))}else{unique_output(dir,&job.project.name)}\n}\n'''
    render = render.replace(anchor, anchor + helper, 1)

    old = 'let out=if smart_repeat_project(job){unique_output(&out_dir,&job.project.name)}else{unique_output(&out_dir,&job.project.name)};'
    new = 'let out=final_output_path(job,&out_dir);'
    if old not in render:
        raise SystemExit('render.rs final output selection anchor missing')
    render = render.replace(old, new, 1)

old_fast = 'let out=unique_output(&out_dir,&job.project.name);'
new_fast = 'let out=render::final_output_path(job,&out_dir);'
if old_fast in fast:
    fast = fast.replace(old_fast, new_fast, 1)
elif new_fast not in fast:
    raise SystemExit('fast_render.rs final output selection anchor missing')

# The fast renderer no longer owns output naming. Remove its duplicate helper so
# there is exactly one final-file naming policy at the renderer boundary.
fast_unique = '''fn unique_output(dir:&Path,name:&str)->PathBuf{let safe=safe_name(name);let mut p=dir.join(format!("{} — Ready Videos.mp4",safe));let mut n=2;while p.exists(){p=dir.join(format!("{} — Ready Videos_{}.mp4",safe,n));n+=1}p}\n'''
if fast_unique in fast:
    fast = fast.replace(fast_unique, '', 1)

RENDER.write_text(render, encoding='utf-8')
FAST.write_text(fast, encoding='utf-8')
print('ENDLUME_VYRON_STABLE_FINAL_FILENAME_PATCH=APPLIED')
