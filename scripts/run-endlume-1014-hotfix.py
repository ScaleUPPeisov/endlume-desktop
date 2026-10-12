#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
path=root/'scripts'/'apply-endlume-1014-hotfix.py'
text=path.read_text(encoding='utf-8')
old='''replace_once(\n    "src/pages/Editors.tsx",\n    "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);};",\n    "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);setPreviewError(undefined);};",\n)'''
new='''text = read("src/pages/Editors.tsx")\nold_invalidate = "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);};"\nnew_invalidate = "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);setPreviewError(undefined);};"\nif text.count(old_invalidate) != 2:\n    raise SystemExit(f"src/pages/Editors.tsx: expected two invalidatePreview blocks before patch, got {text.count(old_invalidate)}")\nwrite("src/pages/Editors.tsx", text.replace(old_invalidate, new_invalidate, 1))'''
if text.count(old)!=2:
    raise SystemExit(f'applicator shape changed: expected two matching replace_once blocks, got {text.count(old)}')
# Only the first block (Effects) needs special handling. The second block then has
# exactly one literal match left and remains a strict replace_once for Subscribe.
text=text.replace(old,new,1)
path.write_text(text,encoding='utf-8')
proc=subprocess.run([sys.executable,str(path)],cwd=root)
raise SystemExit(proc.returncode)
