#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
path=root/'scripts'/'apply-endlume-1014-hotfix.py'
text=path.read_text(encoding='utf-8')

def exact(old:str,new:str,count:int=1):
    global text
    found=text.count(old)
    if found!=count:
        raise SystemExit(f'applicator shape changed: expected {count} matches, got {found}')
    text=text.replace(old,new,1)

# Editors.tsx has the same invalidatePreview literal in Effects and Subscribe.
# Patch the first one deterministically; the original applicator then patches the
# remaining single Subscribe occurrence with strict replace_once semantics.
old='''replace_once(\n    "src/pages/Editors.tsx",\n    "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);};",\n    "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);setPreviewError(undefined);};",\n)'''
new='''text = read("src/pages/Editors.tsx")\nold_invalidate = "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);};"\nnew_invalidate = "  const invalidatePreview=()=>{previewRequest.current+=1;setAssets(undefined);setPreviewSnapshot(undefined);setPreviewError(undefined);};"\nif text.count(old_invalidate) != 2:\n    raise SystemExit(f"src/pages/Editors.tsx: expected two invalidatePreview blocks before patch, got {text.count(old_invalidate)}")\nwrite("src/pages/Editors.tsx", text.replace(old_invalidate, new_invalidate, 1))'''
exact(old,new,2)

# Rust ProjectScanItem gained VYRON routing metadata. Manual scan projects must
# explicitly initialize those optional fields to None or cargo check fails.
anchor='''replace_once(\n    "src-tauri/src/model.rs",\n    "  #[serde(default)] pub selected_effect_id:Option<String>\\n}",\n    "  #[serde(default)] pub selected_effect_id:Option<String>,\\n  #[serde(default)] pub output_dir:Option<String>,\\n  #[serde(default)] pub output_source:Option<String>,\\n  #[serde(default)] pub vyron_manifest_path:Option<String>,\\n  #[serde(default)] pub vyron_channel_name:Option<String>\\n}",\n)'''
scan_patch=anchor+'''\n\nreplace_once(\n    "src-tauri/src/scan.rs",\n    "     audio:audio.into_iter().map(|x|x.to_string_lossy().into_owned()).collect(),valid:error.is_none(),error,anchors:None,selected_effect_id:None\\n   });",\n    "     audio:audio.into_iter().map(|x|x.to_string_lossy().into_owned()).collect(),valid:error.is_none(),error,anchors:None,selected_effect_id:None,\\n     output_dir:None,output_source:None,vyron_manifest_path:None,vyron_channel_name:None\\n   });",\n)'''
exact(anchor,scan_patch,1)

# Keep the manifest destination in persisted settings as restart/recovery fallback.
# Queueing still prefers immutable per-project outputDir, so this cannot overwrite
# an already resolved VYRON destination.
old_bridge='''    "        const st=useApp.getState();st.setDraftProjects(valid);st.setInvalidProjects(invalid);st.setPreviewProjectPath(valid[0]?.path);st.setLastRoot(info.rootPath);st.setPage('project');",'''
new_bridge='''    "        const st=useApp.getState();st.setDraftProjects(valid);st.setInvalidProjects(invalid);st.patchSettings({outputDir:info.outputDir});st.setPreviewProjectPath(valid[0]?.path);st.setLastRoot(info.rootPath);st.setPage('project');",'''
exact(old_bridge,new_bridge,1)

path.write_text(text,encoding='utf-8')
proc=subprocess.run([sys.executable,str(path)],cwd=root)
raise SystemExit(proc.returncode)
