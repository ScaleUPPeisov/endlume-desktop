#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def text(path:str)->str:
    return (ROOT/path).read_text(encoding='utf-8')

editors=text('src/pages/Editors.tsx')
live=text('src-tauri/src/live_preview.rs')
bridge=text('src/components/VyronBatchBridge.tsx')
scan=text('src-tauri/src/scan.rs')

# v2 mutates broad function blocks and one Subscribe error block. Those mutations
# are already present in a tested hotfix branch after the first successful pass.
# Re-running v2 against that state would prepend a second detail/exists declaration.
markers=[
    'const detail=String(error);const exists=detail.includes(\'exists=false\')',
    'FFprobe sidecar preview timeout',
    'ffprobe frame diagnostic timeout',
    'patchSettings({outputDir:info.outputDir})',
    'output_dir:None,output_source:None,vyron_manifest_path:None,vyron_channel_name:None',
]
values=[editors,live,live,bridge,scan]

present=[marker in value for marker,value in zip(markers,values)]
if all(present):
    # The unmount invalidator may have been inserted once by v2. It must never
    # multiply across CI retries.
    hook='  useEffect(()=>()=>{previewRequest.current+=1;},[]);'
    hook_count=editors.count(hook)
    if hook_count not in (0,2):
        raise SystemExit(f'Editors.tsx: invalid preview unmount hook count {hook_count}')
    detail='const detail=String(error);const exists=detail.includes(\'exists=false\')'
    if editors.count(detail)!=1:
        raise SystemExit(f'Editors.tsx: Subscribe detail/exists declaration count is {editors.count(detail)}, expected 1')
    print('ENDLUME 10.0.14 v2 already applied; idempotent retry skips v2 mutations')
    raise SystemExit(0)

if any(present):
    missing=[m for m,p in zip(markers,present) if not p]
    raise SystemExit('ENDLUME 10.0.14 v2 partial state; refusing mixed reapply. Missing: '+', '.join(missing))

subprocess.run([sys.executable,str(ROOT/'scripts'/'run-endlume-1014-hotfix-v2.py')],cwd=ROOT,check=True)

# Verify first application reached exactly the same stable state expected on retries.
editors=text('src/pages/Editors.tsx')
if editors.count("const detail=String(error);const exists=detail.includes('exists=false')")!=1:
    raise SystemExit('Editors.tsx: v2 first pass did not produce exactly one Subscribe detail/exists declaration')
print('ENDLUME 10.0.14 v3 idempotent hotfix pass complete')
