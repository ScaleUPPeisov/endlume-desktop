#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def text(p): return (root/p).read_text(encoding="utf-8")
project=text("src/pages/ProjectPage.tsx")
bridge=text("src/components/VyronBatchBridge.tsx")
vyron=text("src-tauri/src/vyron_bridge.rs")
editors=text("src/pages/Editors.tsx")
live=text("src-tauri/src/live_preview.rs")
composite=text("src/components/LiveCompositePreview.tsx")
model=text("src-tauri/src/model.rs")
assert "outputSource?: 'vyron'|'manual'" in text("src/types.ts")
assert "outputDir:info.outputDir,outputSource:'vyron'" in bridge
assert "setPreviewProjectPath(valid[0]?.path)" in bridge
assert "v.get(\"outputDir\")" in vyron and "validate_output_writable" in vyron
assert "validate_output_scope(&output,batch_root)?" not in vyron
assert "vyron_explicit_output_dir_may_live_outside_workspace" in text("src-tauri/src/vyron_bridge_tests.rs")
assert "const groups=new Map<string,typeof queuedProjects>()" in project
assert "AUTO • VYRON" in project
assert "selectedForAll" in project and "СБРОСИТЬ → БЕЗ ЭФФЕКТА" in project
assert "previewWithTimeout" in editors and "ПОВТОРИТЬ" in editors and "ВЫБРАТЬ ЗАНОВО" in editors
assert "poster optional" in composite.lower() or "POSTER_OPTIONAL" in composite
assert "PREVIEW_PROCESS_TIMEOUT" in live and "[preview/request]" in live and "[preview/decode]" in live
assert "output_dir:Option<String>" in model
assert "output_dir:None,output_source:None" in text("src-tauri/src/scan.rs")
assert "patchSettings({outputDir:info.outputDir})" in bridge
assert "FFprobe sidecar preview timeout" in live and "ffprobe frame diagnostic timeout" in live
assert "Файл существует: ${exists}" in editors
print("PASS: ENDLUME 10.0.14 source contracts")
