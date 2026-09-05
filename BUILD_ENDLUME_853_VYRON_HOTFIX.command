#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_852_PROMOTE.command"
TMP="$(mktemp /tmp/endlume-853-vyron-hotfix.XXXXXX.command)"
cleanup(){ rm -f "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
[[ -f "$BASE" ]] || { echo '❌ ENDLUME 8.53: 8.52 production builder missing' >&2; exit 1; }
python3 - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()
old_version='EXPECTED_VERSION="1.0.0-alpha.8.52"'
old_pin='PINNED_SHA="03399cf0f12b912a846144cd4d060755b5260cc5"'
if old_version not in src or old_pin not in src:
    raise SystemExit('ENDLUME 8.53: base builder identity anchors missing')
src=src.replace(old_version,'EXPECTED_VERSION="1.0.0-alpha.8.53"',1)
src=src.replace(old_pin,'PINNED_SHA="3609028e2540d85b64a02c169fe5203735ae3a1c"',1)
# 8.53 is deliberately bridge-only. The exact 8.52 render blob must remain byte-identical.
anchor="grep -Fq 'mp4_manifest::expand_video_prefix_cycle' src-tauri/src/render.rs || fail \"8.52 zero-copy manifest path missing\"\n"
if anchor not in src:
    raise SystemExit('ENDLUME 8.53: render guard anchor missing')
bridge=r'''[[ "$(git hash-object src-tauri/src/render.rs)" = "9e011adc207872a23105e525a9d5bdab27242b5f" ]] || fail "8.52 render.rs changed in VYRON-only hotfix"
grep -Fq 'mod vyron_bridge;' src-tauri/src/lib.rs || fail "VYRON native module missing"
grep -Fq 'vyron_bridge::consume_vyron_batch_request' src-tauri/src/lib.rs || fail "VYRON consume command missing"
grep -Fq 'vyron_bridge::load_vyron_batch_manifest' src-tauri/src/lib.rs || fail "VYRON manifest command missing"
grep -Fq 'vyron_bridge::report_vyron_render' src-tauri/src/lib.rs || fail "VYRON status command missing"
grep -Fq "consumeVyronBatch:()=>invoke<VyronBatchRequest|null>('consume_vyron_batch_request')" src/tauri.ts || fail "VYRON frontend invoke missing"
grep -Fq '<VyronBatchBridge/>' src/pages/App.tsx || fail "VYRON bridge component is not mounted"
grep -Fq 'join("VYRON Inbox")' src-tauri/src/vyron_bridge.rs || fail "VYRON inbox contract missing"
'''
src=src.replace(anchor,anchor+bridge,1)
# Keep the corrected sequential-decoding repeat-frame gate from 8.52 R2.
start='"$FFMPEG" -hide_banner -loglevel error -i "$GATE/final.mov" -map 0:a:0 -t 8 -f null -\n'
end='SEED_BYTES="$(stat -f%z "$GATE/seed.mov")"; FINAL_BYTES="$(stat -f%z "$GATE/final.mov")"\n'
a=src.find(start); b=src.find(end,a+len(start))
if a<0 or b<0:
    raise SystemExit('ENDLUME 8.53: physical repeat-frame gate anchors not found')
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
src=src.replace('ENDLUME STUDIO 8.52 exact source built and signed','ENDLUME STUDIO 8.53 VYRON acceptance hotfix built and signed')
src=src.replace('periodic zero-copy MP4 path passed Rust + FFprobe + audio + AVFoundation gates','VYRON acceptance restored; periodic zero-copy MP4 path revalidated unchanged')
Path(sys.argv[2]).write_text(src)
PY
chmod +x "$TMP"
/bin/bash "$TMP"
