#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_852_PROMOTE.command"
TMP="$(mktemp /tmp/endlume-852-promote-r2.XXXXXX.command)"
cleanup(){ rm -f "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
[[ -f "$BASE" ]] || { echo '❌ ENDLUME 8.52 R2: base builder missing' >&2; exit 1; }
python3 - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()
start='"$FFMPEG" -hide_banner -loglevel error -i "$GATE/final.mov" -map 0:a:0 -t 8 -f null -\n'
end='SEED_BYTES="$(stat -f%z "$GATE/seed.mov")"; FINAL_BYTES="$(stat -f%z "$GATE/final.mov")"\n'
a=src.find(start)
b=src.find(end,a+len(start))
if a<0 or b<0:
    raise SystemExit('ENDLUME 8.52 R2: physical repeat-frame gate anchors not found')
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
fixed=src[:a]+replacement+src[b:]
Path(sys.argv[2]).write_text(fixed)
PY
chmod +x "$TMP"
/bin/bash "$TMP"
