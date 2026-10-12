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

live_preview=text("src-tauri/src/live_preview.rs")
assert 'mode=bundle-direct' in live_preview
assert '@executable_path/../Frameworks' in live_preview
assert 'ENDLUME_PREVIEW_HW_TIMEOUT_DIRECT_SAFE_FALLBACK' in live_preview
assert 'safe_prefix.as_ref()' in live_preview
assert 'if hw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(hw_error)}' not in live_preview

# The physical gate owns the metadata-vs-count_frames split. Lock the Rust
# lifetime fix here so a later edit cannot reintroduce E0716 before physical QA.
probe_fixer=text("scripts/fix-endlume-1014-preview-probe.py")
assert 'let out_arg=out.to_string_lossy().into_owned()' in probe_fixer
assert 'ENDLUME_PREVIEW_PROBE_MODE=' in probe_fixer
assert 'let probe_valid=if deep_probe' in probe_fixer

live_preview=text("src-tauri/src/live_preview.rs")
assert 'mode=bundle-direct' in live_preview
assert '@executable_path/../Frameworks' in live_preview
assert 'ENDLUME_PREVIEW_HW_TIMEOUT_DIRECT_SAFE_FALLBACK' in live_preview
assert 'safe_prefix.as_ref()' in live_preview
assert 'if hw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(hw_error)}' not in live_preview
canonical_preview=text("src-tauri/src/preview.rs")
assert 'ENDLUME_PREVIEW_CANONICAL_TIMEOUT_SHORT_FALLBACK' in canonical_preview
assert '"-t","0.75","-c:v","libx264"' in canonical_preview
assert 'primary.extend(vec!["-t","3.0"]' in canonical_preview
