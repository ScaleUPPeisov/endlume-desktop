#!/usr/bin/env python3
from pathlib import Path
import json,re

ROOT=Path(__file__).resolve().parents[1]
VERSION="1.0.0-alpha.8.65"

def read(p): return (ROOT/p).read_text(errors="replace")

pkg=json.loads(read("package.json"))
lock=json.loads(read("package-lock.json"))
tauri=json.loads(read("src-tauri/tauri.conf.json"))
cargo=read("src-tauri/Cargo.toml")
cargo_lock=read("src-tauri/Cargo.lock")
queue=read("src-tauri/src/queue.rs")
qstate=read("src/queue-state.ts")
render=read("src-tauri/src/render.rs")
app=read("src/pages/App.tsx")
ux=read("src/components/EndlumeUpdateExperience.tsx")
render_page=read("src/pages/RenderPage.tsx")
system=read("src-tauri/src/system.rs")
settings=read("src/pages/SettingsPage.tsx")
history=read("src/components/ReleaseHistory.tsx")

assert pkg["version"]==VERSION
assert lock["version"]==VERSION and lock["packages"][""]["version"]==VERSION
assert tauri["version"]==VERSION
assert re.search(r'^version\s*=\s*"'+re.escape(VERSION)+r'"$',cargo,re.M)
assert f'name = "endlume"\nversion = "{VERSION}"' in cargo_lock
assert VERSION in settings and f"version:'{VERSION}'" in history

# Exact success result metadata must come from RenderOutcome, not a guessed directory rescan.
success=queue[queue.index("Ok(summary)=>"):queue.index("Err(error) if",queue.index("Ok(summary)=>"))]
assert '"resultPath":summary.output_path' in success
assert '"resultBytes":summary.output_bytes' in success
assert '"encoder":summary.encoder' in success
assert "done_fallback_payload(&job)" not in success

# Late terminal snapshots are not allowed to erase valid result metadata.
terminal=qstate[qstate.index("if(isTerminal(project.status))"):qstate.index("const merged:any",qstate.index("if(isTerminal(project.status))"))]
for field in ["resultPath","resultBytes","actualVideoBitrate","encoder","startedAt","elapsedSec"]:
    assert field in terminal
assert "safePatch[key]===null||safePatch[key]===undefined" in terminal

# Plain one-image production jobs must use the short physical still/sample-table path.
assert 'reason!="FAST_ONE_IMAGE"' in render
assert "!has_effects&&!has_subs" in render
assert "PHYSICAL_FRAMES_PER_STILL:usize=30" in render
assert "if clips.len()==1" in render
assert "FAST_ONE_IMAGE / MULTI_STILL zero-copy готов" in render

# Result UI contract.
assert "Размер файла: {fmtBytes(active.resultBytes)}" in render_page
assert 'disabled={!active.resultPath}' in render_page
assert "openResult(active.resultPath)" in render_page
assert "revealResult(active.resultPath)" in render_page
assert "project-scan','encoder-detection','strict-visual-master','strict-audio-mux','ffprobe-validation" in render_page
assert 'pub fn open_result_path' in system and 'pub fn reveal_result_path' in system

# Homer splash must be visible on every startup long enough to be perceived.
assert "startupMinElapsed" in app
assert "1150" in app
assert "if(!startupMinElapsed||!license)return <StartupSplash/>" in app
assert "ENDLUME YT Studio PEISOV" in ux
assert "Long Video Engine" in ux
assert "endlume-homer.png" in ux

print("ENDLUME_865_SOURCE_CONTRACT_GREEN")
