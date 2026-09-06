#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_852_PROMOTE.command"
TMP="$(mktemp /tmp/endlume-858-final-integrated.XXXXXX.command)"
cleanup(){ rm -f "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
[[ -f "$BASE" ]] || { echo '❌ ENDLUME 8.58: 8.52 production builder missing' >&2; exit 1; }

python3 - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()
old_version='EXPECTED_VERSION="1.0.0-alpha.8.52"'
old_pin='PINNED_SHA="03399cf0f12b912a846144cd4d060755b5260cc5"'
if old_version not in src or old_pin not in src:
    raise SystemExit('ENDLUME 8.58: base builder identity anchors missing')
src=src.replace(old_version,'EXPECTED_VERSION="1.0.0-alpha.8.58"',1)
src=src.replace(old_pin,'PINNED_SHA="abdbe27a73be6a17d9d409599971cc3ef15840c9"',1)

# Build exactly the integrated source that passed the final physical M1 gate.
cd_anchor='cd "$SRC"\n'
if src.count(cd_anchor)!=1:
    raise SystemExit('ENDLUME 8.58: source checkout anchor missing')
src=src.replace(cd_anchor,cd_anchor+'python3 scripts/apply-render-isolation-8-56.py\npython3 scripts/apply-master-frame-hotfix-8-57.py\npython3 scripts/apply-queue-finalization-hotfix-8-58.py\n',1)

# Permanent production contracts: 8.57 render/media core + 8.58 queue/VYRON control plane.
anchor="grep -Fq 'mp4_manifest::expand_video_prefix_cycle' src-tauri/src/render.rs || fail \"8.52 zero-copy manifest path missing\"\n"
if anchor not in src:
    raise SystemExit('ENDLUME 8.58: render guard anchor missing')
guards=r'''grep -Fq 'resolved_job.settings.duration_mode="whole-track".into();' src-tauri/src/render.rs || fail "whole-track lock missing"
grep -Fq 'resolved_job.settings.crossfade_sec=0.0;' src-tauri/src/render.rs || fail "crossfade disable missing"
! grep -Fq 'if t-target<=240.0' src-tauri/src/render.rs || fail "whole-track cut cap returned"
grep -Fq 'prepare_strict_856' src-tauri/src/cache.rs || fail "lossless Effects cache missing"
grep -Fq 'start_strict_prewarm_856' src-tauri/src/lib.rs || fail "Effects prewarm missing"
grep -Fq 'render_zero_sub_zero_copy_856' src-tauri/src/render.rs || fail "zero-Subscribe zero-copy path missing"
grep -Fq 'shortest=0:repeatlast=1:eof_action=repeat' src-tauri/src/render.rs || fail "Effects lifetime fix missing"
grep -Fq 'const STRICT_857_MAX_GOP_FRAMES:u32=1800;' src-tauri/src/render.rs || fail "safe VideoToolbox GOP missing"
grep -Fq 'encoder=="hevc_videotoolbox"{frames.min(STRICT_857_MAX_GOP_FRAMES)}else{frames}' src-tauri/src/render.rs || fail "VideoToolbox-only GOP cap missing"
grep -Fq 'async fn probe_video_packets_857' src-tauri/src/render.rs || fail "packet integrity probe missing"
grep -Fq 'Strict 8.57 master integrity' src-tauri/src/render.rs || fail "master frame+packet integrity gate missing"
grep -Fq 'verify_strict_857_result' src-tauri/src/render.rs || fail "final strict verifier missing"
grep -Fq 'let max_attempts=if smart_repeat_project(job){1}else{2};' src-tauri/src/render.rs || fail "one-image single-attempt lock missing"
grep -Fq 'software fallback отключён' src-tauri/src/render.rs || fail "strict software fallback guard missing"
grep -Fq 'STRICT_856_MIN_BYTES:u64=500_000_000' src-tauri/src/render.rs || fail "500 MB production minimum missing"
grep -Fq 'STRICT_856_PAD_TARGET_BYTES:u64=500_000_000' src-tauri/src/render.rs || fail "500 MB pad target missing"
grep -Fq 'STRICT_856_MAX_BYTES:u64=700_000_000' src-tauri/src/render.rs || fail "700 MB production maximum missing"
grep -Fq 'Strict Fidelity: исходную музыку нельзя сохранить bitstream-copy' src-tauri/src/render.rs || fail "original MP3 bitstream-copy contract missing"
# 8.58 queue terminal self-heal / monotonic completion.
grep -Fq 'progressPending.delete(p.id)' src/pages/App.tsx || fail "late 97 percent RAF guard missing"
grep -Fq 'finished:Mutex<VecDeque<Value>>' src-tauri/src/queue.rs || fail "backend terminal memory missing"
grep -Fq 'fn latest_result_for_job' src-tauri/src/queue.rs || fail "terminal result recovery missing"
grep -Fq 'runtime.remember_terminal(done_fallback_payload(&job))' src-tauri/src/queue.rs || fail "successful terminal ack missing"
grep -Fq '"finished":finished' src-tauri/src/queue.rs || fail "terminal snapshot missing"
grep -Fq 'const finished=Array.isArray(snapshot?.finished)?snapshot.finished:[]' src/queue-state.ts || fail "frontend terminal snapshot apply missing"
# Integrated VYRON render library; renderer itself remains settings-driven.
grep -Fq 'fn safe_channel_folder' src-tauri/src/vyron_bridge.rs || fail "VYRON channel folder sanitization missing"
grep -Fq 'fn vyron_workspace_root' src-tauri/src/vyron_bridge.rs || fail "VYRON workspace resolver missing"
grep -Fq 'workspace.join("Render").join(safe_channel_folder(channel_name))' src-tauri/src/vyron_bridge.rs || fail "VYRON Render/channel output missing"
grep -Fq 'let output=resolve_render_output(&v,&root,&channel_name)?;' src-tauri/src/vyron_bridge.rs || fail "VYRON render-library resolver missing"
grep -Fq 'source_manifest_path' src-tauri/src/vyron_bridge.rs || fail "VYRON sourceManifestPath support missing"
grep -Fq 'selected_project_ids' src-tauri/src/vyron_bridge.rs || fail "VYRON selectedProjectIds support missing"
grep -Fq 'handoff_source' src-tauri/src/vyron_bridge.rs || fail "VYRON handoff resolver missing"
grep -Fq 'files.sort_by_key(|p|std::cmp::Reverse' src-tauri/src/vyron_bridge.rs || fail "VYRON newest-first inbox handling missing"
grep -Fq '<VyronBatchBridge/>' src/pages/App.tsx || fail "VYRON bridge component missing"
grep -Fq 'st.patchSettings({outputDir:info.outputDir})' src/components/VyronBatchBridge.tsx || fail "VYRON outputDir handoff missing"
# Original approved icon: transparent cyan/violet/magenta infinity, no black rounded square.
grep -Fq 'Original ENDLUME identity: only the cyan/violet/magenta infinity mark' scripts/generate-icon-8-32.swift || fail "approved icon generator missing"
python3 - <<'PYCONTRACT'
import json,re,subprocess
assert json.load(open('package.json'))['version']=='1.0.0-alpha.8.58'
assert json.load(open('src-tauri/tauri.conf.json'))['version']=='1.0.0-alpha.8.58'
c=open('src-tauri/Cargo.toml').read(); assert re.search(r'^version\s*=\s*"1\.0\.0-alpha\.8\.58"$',c,re.M)
ui=open('src/pages/SettingsPage.tsx').read(); assert 'ENDLUME Studio 1.0.0-alpha.8.58' in ui
hist=open('src/components/ReleaseHistory.tsx').read(); assert "version:'1.0.0-alpha.8.58'" in hist
alpha=subprocess.check_output(['/usr/bin/sips','-g','hasAlpha','src-tauri/icons/icon.png'],text=True).lower()
assert 'yes' in alpha,alpha
PYCONTRACT
'''
src=src.replace(anchor,anchor+guards,1)

# Re-run queue/VYRON/MP4 regression tests in the exact production source.
frontend_anchor='npm ci\nnpm run check\nnpm run build\n'
if src.count(frontend_anchor)!=1:
    raise SystemExit('ENDLUME 8.58: frontend gate anchor missing')
frontend=r'''npm ci
npm run check
rm -rf .queue-test-dist
./node_modules/.bin/tsc src/queue-state.ts --target ES2022 --module ES2022 --moduleResolution Bundler --skipLibCheck --outDir .queue-test-dist --noEmit false
node scripts/test-queue-finalization-8-58.mjs "$SRC/.queue-test-dist/queue-state.js"
npm run build
'''
src=src.replace(frontend_anchor,frontend,1)

test_anchor='cargo test --manifest-path src-tauri/Cargo.toml mp4_manifest::tests -- --nocapture\n'
if src.count(test_anchor)!=1:
    raise SystemExit('ENDLUME 8.58: MP4 test anchor missing')
src=src.replace(test_anchor,test_anchor+'cargo test --manifest-path src-tauri/Cargo.toml vyron_ -- --nocapture\n',1)

# Keep the reliable sequential-decode repeat-frame gate; single-frame -ss probing is not valid for this edit-list layout.
start='"$FFMPEG" -hide_banner -loglevel error -i "$GATE/final.mov" -map 0:a:0 -t 8 -f null -\n'
end='SEED_BYTES="$(stat -f%z "$GATE/seed.mov")"; FINAL_BYTES="$(stat -f%z "$GATE/final.mov")"\n'
a=src.find(start); b=src.find(end,a+len(start))
if a<0 or b<0:
    raise SystemExit('ENDLUME 8.58: physical repeat-frame gate anchors not found')
replacement=start+r'''"$FFMPEG" -hide_banner -loglevel error -i "$GATE/final.mov" -map 0:v:0 -f null -
"$FFMPEG" -hide_banner -loglevel error -i "$GATE/video.mp4" -map 0:v:0 -f framemd5 - > "$GATE/source.md5"
"$FFMPEG" -hide_banner -loglevel error -i "$GATE/final.mov" -map 0:v:0 -f framemd5 - > "$GATE/final.md5"
python3 - "$GATE/source.md5" "$GATE/final.md5" <<'PYHASH'
import sys
def hashes(path):
    return [line.split(',')[-1].strip() for line in open(path) if line[:1].isdigit()]
src=hashes(sys.argv[1]); out=hashes(sys.argv[2])
assert len(src)==8,len(src)
assert len(out)==16,len(out)
expected=src[:4]+src[4:8]+src[4:8]+src[4:8]
assert out==expected,[(i,a,b) for i,(a,b) in enumerate(zip(out,expected)) if a!=b][:8]
print('PASS: repeated frames match exact source samples in sequential decode')
PYHASH
'''
src=src[:a]+replacement+src[b:]

src=src.replace('ENDLUME STUDIO 8.52 exact source built and signed','ENDLUME STUDIO 8.58 final integrated source built and signed')
src=src.replace('VideoToolbox q100/500k hardware-first; x265 CRF18/500k fallback','VideoToolbox q100 hardware-only for strict one-image render; GOP <=1800; no libx265 retry/reset')
src=src.replace('periodic zero-copy MP4 path passed Rust + FFprobe + audio + AVFoundation gates','queue 40/40 + VYRON Render/channel + 3381/3381 integrity + whole-track MP3 + 500-700 MB + zero-copy gates passed')
Path(sys.argv[2]).write_text(src)
PY

chmod +x "$TMP"
/bin/bash "$TMP"
