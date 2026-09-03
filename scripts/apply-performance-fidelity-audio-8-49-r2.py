#!/usr/bin/env python3
from pathlib import Path

base=Path(__file__).with_name('apply-performance-fidelity-audio-8-49.py')
src=base.read_text(encoding='utf-8')
old="anchor='fn render_diag_path(job:&QueueJob)->Option<PathBuf>{'"
new="anchor='async fn output(app:&AppHandle,name:&str,args:Vec<String>)'"
if old not in src:
    raise SystemExit('8.49-r2: old migration anchor declaration missing')
src=src.replace(old,new,1)
src=src.replace("'render_diag_path anchor missing'","'verified output() insertion anchor missing'",1)
# Execute the canonical migration after only the anchor normalization above.
# sys.argv is intentionally preserved, so the workspace argument is unchanged.
exec(compile(src,str(base),'exec'),{'__name__':'__main__','__file__':str(base)})
