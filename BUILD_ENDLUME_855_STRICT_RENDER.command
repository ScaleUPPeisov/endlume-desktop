#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_852_PROMOTE.command"
TMP="$(mktemp /tmp/endlume-855-strict-render.XXXXXX.command)"
cleanup(){ rm -f "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
[[ -f "$BASE" ]] || { echo '❌ ENDLUME 8.55: 8.52 production builder missing' >&2; exit 1; }

python3 - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()
old_version='EXPECTED_VERSION="1.0.0-alpha.8.52"'
old_pin='PINNED_SHA="03399cf0f12b912a846144cd4d060755b5260cc5"'
if old_version not in src or old_pin not in src:
    raise SystemExit('ENDLUME 8.55: base builder identity anchors missing')
src=src.replace(old_version,'EXPECTED_VERSION="1.0.0-alpha.8.55"',1)
src=src.replace(old_pin,'PINNED_SHA="23cb01908604cf7583843c1b1bf74eafa7205a69"',1)

# The pinned source is deliberately the already-gated 8.54 source plus the deterministic 8.55 migration.
cd_anchor='cd "$SRC"\n'
if src.count(cd_anchor)!=1:
    raise SystemExit('ENDLUME 8.55: source checkout anchor missing')
src=src.replace(cd_anchor,cd_anchor+'python3 scripts/apply-strict-render-contract-8-55.py\n',1)

# Permanent strict-render and VYRON contract gates.
anchor="grep -Fq 'mp4_manifest::expand_video_prefix_cycle' src-tauri/src/render.rs || fail \"8.52 zero-copy manifest path missing\"\n"
if anchor not in src:
    raise SystemExit('ENDLUME 8.55: render guard anchor missing')
guards=r'''grep -Fq 'resolved_job.settings.duration_mode="whole-track".into();' src-tauri/src/render.rs || fail "whole-track lock missing"
grep -Fq 'resolved_job.settings.crossfade_sec=0.0;' src-tauri/src/render.rs || fail "crossfade disable missing"
grep -Fq 'STRICT_855_MIN_BYTES:u64=400_000_000' src-tauri/src/render.rs || fail "400 MB minimum gate missing"
grep -Fq 'STRICT_855_MAX_BYTES:u64=700_000_000' src-tauri/src/render.rs || fail "700 MB maximum gate missing"
grep -Fq 'STRICT_855_MASTER_SECONDS:f64=30.0' src-tauri/src/render.rs || fail "30 second master gate missing"
grep -Fq 'render_zero_sub_zero_copy_855' src-tauri/src/render.rs || fail "zero-Subscribe zero-copy path missing"
grep -Fq 'Strict Fidelity: исходную музыку нельзя сохранить bitstream-copy' src-tauri/src/render.rs || fail "original MP3 bitstream-copy contract missing"
! grep -Fq 'if t-target<=240.0' src-tauri/src/render.rs || fail "whole-track 240-second cut cap returned"
python3 - <<'PYCONTRACT'
import json
c=json.load(open('release/ENDLUME_PRODUCTION_CONTRACT.json'))
assert c.get('immutable') is True
w=c['oneImageWorkflow']
assert w['expectedAudioTracks']==15
assert w['resolution']=='1920x1080' and w['fps']==60 and w['codec']=='h265'
assert w['renderWallSecondsMin']==20 and w['renderWallSecondsMax']==30
assert w['outputBytesMin']==400000000 and w['outputBytesMax']==700000000
m=w['music']; assert m['allowReencode'] is False and m['allowMidTrackCut'] is False and m['finishCurrentTrackAfterNominalDuration'] is True
assert c['integrations']['vyronHandoffMustRemainCompatible'] is True
assert c['changePolicy']['unrelatedFunctionalChangesAllowed'] is False
PYCONTRACT
grep -Fq 'mod vyron_bridge;' src-tauri/src/lib.rs || fail "VYRON native module missing"
grep -Fq 'vyron_bridge::consume_vyron_batch_request' src-tauri/src/lib.rs || fail "VYRON consume command missing"
grep -Fq 'vyron_bridge::load_vyron_batch_manifest' src-tauri/src/lib.rs || fail "VYRON manifest command missing"
grep -Fq 'vyron_bridge::report_vyron_render' src-tauri/src/lib.rs || fail "VYRON status command missing"
grep -Fq 'source_manifest_path' src-tauri/src/vyron_bridge.rs || fail "VYRON sourceManifestPath support missing"
grep -Fq 'selected_project_ids' src-tauri/src/vyron_bridge.rs || fail "VYRON selectedProjectIds support missing"
grep -Fq 'handoff_source' src-tauri/src/vyron_bridge.rs || fail "VYRON handoff resolver missing"
grep -Fq 'files.sort_by_key(|p|std::cmp::Reverse' src-tauri/src/vyron_bridge.rs || fail "VYRON newest-first inbox handling missing"
grep -Fq 'Duration::from_secs(5)' src-tauri/src/vyron_bridge.rs || fail "VYRON stale request cleanup missing"
grep -Fq 'req.selectedProjectIds||[]' src/components/VyronBatchBridge.tsx || fail "VYRON selected project frontend bridge missing"
grep -Fq "loadVyronBatch:(manifestPath:string,selectedProjectIds:string[]=[])" src/tauri.ts || fail "VYRON selected project invoke missing"
grep -Fq '<VyronBatchBridge/>' src/pages/App.tsx || fail "VYRON bridge component is not mounted"
grep -Fq 'join("VYRON Inbox")' src-tauri/src/vyron_bridge.rs || fail "VYRON inbox contract missing"
'''
src=src.replace(anchor,anchor+guards,1)

# The production build must rerun the VYRON tests in addition to the MP4 manifest tests.
test_anchor='cargo test --manifest-path src-tauri/Cargo.toml mp4_manifest::tests -- --nocapture\n'
if src.count(test_anchor)!=1:
    raise SystemExit('ENDLUME 8.55: MP4 test anchor missing')
src=src.replace(test_anchor,test_anchor+'cargo test --manifest-path src-tauri/Cargo.toml vyron_ -- --nocapture\n',1)

# Carry forward the 8.54 sequential decode frame-identity gate. Single-frame -ss probing is not reliable for this manifest layout.
start='"$FFMPEG" -hide_banner -loglevel error -i "$GATE/final.mov" -map 0:a:0 -t 8 -f null -\n'
end='SEED_BYTES="$(stat -f%z "$GATE/seed.mov")"; FINAL_BYTES="$(stat -f%z "$GATE/final.mov")"\n'
a=src.find(start); b=src.find(end,a+len(start))
if a<0 or b<0:
    raise SystemExit('ENDLUME 8.55: physical repeat-frame gate anchors missing')
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

src=src.replace('ENDLUME STUDIO 8.52 exact source built and signed','ENDLUME STUDIO 8.55 strict render source built and signed')
src=src.replace('periodic zero-copy MP4 path passed Rust + FFprobe + audio + AVFoundation gates','strict whole-track/original-MP3/400-700MB zero-copy source validated; VYRON tests passed; MP4 path revalidated')
Path(sys.argv[2]).write_text(src)
PY

chmod +x "$TMP"
/bin/bash "$TMP"
