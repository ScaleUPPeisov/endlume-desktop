#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_852_PROMOTE.command"
TMP="$(mktemp /tmp/endlume-856-render-isolation.XXXXXX.command)"
cleanup(){ rm -f "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
[[ -f "$BASE" ]] || { echo '❌ ENDLUME 8.56: 8.52 production builder missing' >&2; exit 1; }

python3 - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()
old_version='EXPECTED_VERSION="1.0.0-alpha.8.52"'
old_pin='PINNED_SHA="03399cf0f12b912a846144cd4d060755b5260cc5"'
if old_version not in src or old_pin not in src:
    raise SystemExit('ENDLUME 8.56: base builder identity anchors missing')
src=src.replace(old_version,'EXPECTED_VERSION="1.0.0-alpha.8.56"',1)
src=src.replace(old_pin,'PINNED_SHA="c12043d9660bc68c5cadc6f68e2385cfc969c11c"',1)

# Build exactly the candidate that passed the M1 gate, then apply its deterministic migration.
cd_anchor='cd "$SRC"\n'
if src.count(cd_anchor)!=1:
    raise SystemExit('ENDLUME 8.56: source checkout anchor missing')
src=src.replace(cd_anchor,cd_anchor+'python3 scripts/apply-render-isolation-8-56.py\n',1)

# Permanent contract: render engine is independent of VYRON; VYRON is only a handoff bridge.
anchor="grep -Fq 'mp4_manifest::expand_video_prefix_cycle' src-tauri/src/render.rs || fail \"8.52 zero-copy manifest path missing\"\n"
if anchor not in src:
    raise SystemExit('ENDLUME 8.56: render guard anchor missing')
guards=r'''grep -Fq 'resolved_job.settings.duration_mode="whole-track".into();' src-tauri/src/render.rs || fail "whole-track lock missing"
grep -Fq 'resolved_job.settings.crossfade_sec=0.0;' src-tauri/src/render.rs || fail "crossfade disable missing"
! grep -Fq 'if t-target<=240.0' src-tauri/src/render.rs || fail "whole-track cut cap returned"
grep -Fq 'prepare_strict_856' src-tauri/src/cache.rs || fail "8.56 lossless Effects cache missing"
grep -Fq 'start_strict_prewarm_856' src-tauri/src/lib.rs || fail "8.56 Effects prewarm missing"
grep -Fq 'render_zero_sub_zero_copy_856' src-tauri/src/render.rs || fail "8.56 zero-Subscribe zero-copy path missing"
grep -Fq 'let max_attempts=if smart_repeat_project(job){1}else{2};' src-tauri/src/render.rs || fail "one-image single-attempt lock missing"
grep -Fq 'software fallback отключён' src-tauri/src/render.rs || fail "libx265 fallback guard missing"
grep -Fq 'STRICT_856_MIN_BYTES:u64=400_000_000' src-tauri/src/render.rs || fail "400 MB minimum missing"
grep -Fq 'STRICT_856_MAX_BYTES:u64=700_000_000' src-tauri/src/render.rs || fail "700 MB maximum missing"
grep -Fq 'Strict Fidelity: исходную музыку нельзя сохранить bitstream-copy' src-tauri/src/render.rs || fail "original MP3 bitstream-copy contract missing"
# VYRON source is frozen and must remain the already-tested 8.54 bridge.
grep -Fq 'source_manifest_path' src-tauri/src/vyron_bridge.rs || fail "VYRON sourceManifestPath support missing"
grep -Fq 'selected_project_ids' src-tauri/src/vyron_bridge.rs || fail "VYRON selectedProjectIds support missing"
grep -Fq 'handoff_source' src-tauri/src/vyron_bridge.rs || fail "VYRON handoff resolver missing"
grep -Fq 'files.sort_by_key(|p|std::cmp::Reverse' src-tauri/src/vyron_bridge.rs || fail "VYRON newest-first inbox handling missing"
grep -Fq '<VyronBatchBridge/>' src/pages/App.tsx || fail "VYRON bridge component missing"
# Original approved icon: transparent cyan/violet/magenta infinity, no black rounded square.
grep -Fq 'Original ENDLUME identity: only the cyan/violet/magenta infinity mark' scripts/generate-icon-8-32.swift || fail "approved icon generator missing"
python3 - <<'PYCONTRACT'
import json,re,subprocess
assert json.load(open('package.json'))['version']=='1.0.0-alpha.8.56'
assert json.load(open('src-tauri/tauri.conf.json'))['version']=='1.0.0-alpha.8.56'
c=open('src-tauri/Cargo.toml').read(); assert re.search(r'^version\s*=\s*"1\.0\.0-alpha\.8\.56"$',c,re.M)
alpha=subprocess.check_output(['/usr/bin/sips','-g','hasAlpha','src-tauri/icons/icon.png'],text=True).lower()
assert 'yes' in alpha,alpha
PYCONTRACT
'''
src=src.replace(anchor,anchor+guards,1)

# Re-run VYRON regression tests in the production build.
test_anchor='cargo test --manifest-path src-tauri/Cargo.toml mp4_manifest::tests -- --nocapture\n'
if src.count(test_anchor)!=1:
    raise SystemExit('ENDLUME 8.56: MP4 test anchor missing')
src=src.replace(test_anchor,test_anchor+'cargo test --manifest-path src-tauri/Cargo.toml vyron_ -- --nocapture\n',1)

# Keep the reliable sequential-decode repeat-frame gate; single-frame -ss probing is not valid for this edit-list layout.
start='"$FFMPEG" -hide_banner -loglevel error -i "$GATE/final.mov" -map 0:a:0 -t 8 -f null -\n'
end='SEED_BYTES="$(stat -f%z "$GATE/seed.mov")"; FINAL_BYTES="$(stat -f%z "$GATE/final.mov")"\n'
a=src.find(start); b=src.find(end,a+len(start))
if a<0 or b<0:
    raise SystemExit('ENDLUME 8.56: physical repeat-frame gate anchors not found')
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

src=src.replace('ENDLUME STUDIO 8.52 exact source built and signed','ENDLUME STUDIO 8.56 render-isolation source built and signed')
src=src.replace('VideoToolbox q100/500k hardware-first; x265 CRF18/500k fallback','VideoToolbox q100 hardware-only for strict one-image render; no libx265 retry/reset')
src=src.replace('periodic zero-copy MP4 path passed Rust + FFprobe + audio + AVFoundation gates','whole-track original-MP3 + zero-copy MP4 + VYRON + original-icon gates passed')
Path(sys.argv[2]).write_text(src)
PY

chmod +x "$TMP"
/bin/bash "$TMP"
