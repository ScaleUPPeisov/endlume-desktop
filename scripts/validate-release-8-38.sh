#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
fail(){ echo "FAIL: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }

RUST=src-tauri/src/render.rs
STORE=src/store.ts
PKG=package.json
for f in "$RUST" "$STORE" "$PKG"; do test -f "$f" || fail "missing $f"; done

grep -Fq 'resolved_job.settings.width=1920;' "$RUST" || fail 'runtime width is not locked to 1920'
grep -Fq 'resolved_job.settings.height=1080;' "$RUST" || fail 'runtime height is not locked to 1080'
grep -Fq 'force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop=' "$RUST" || fail 'YouTube fill + crop pipeline missing'
BASE_LINE="$(grep -F 'fn base_filter' "$RUST" | head -1 || true)"
[[ "$BASE_LINE" == *'force_original_aspect_ratio=increase'* ]] || fail 'base_filter is not cover/increase'
[[ "$BASE_LINE" == *'crop='* ]] || fail 'base_filter crop missing'
[[ "$BASE_LINE" != *'pad='* ]] || fail 'base_filter still contains pad/letterbox'
[[ "$BASE_LINE" != *'force_original_aspect_ratio=decrease'* ]] || fail 'base_filter still uses fit/decrease'
grep -Fq "width:1920,height:1080,fps:30,codec:'h265'" "$STORE" || fail '1080p defaults missing'
grep -Fq '"version": "1.0.0-alpha.8.38"' "$PKG" || fail 'package version is not 8.38'
pass 'runtime is exact 1920x1080 cover/crop with no pad'

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FILTER='scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop=1920:1080:(iw-ow)/2:(ih-oh)/2,setsar=1'

edge_avg(){
  local file="$1" crop="$2"
  "$FFPROBE" -v error -f lavfi -i "movie=$file,$crop,signalstats" -show_entries frame_tags=lavfi.signalstats.YAVG -of default=nw=1:nk=1 | head -1
}
check_frame(){
  local name="$1" size="$2" out="$TMP/$name.png"
  "$FFMPEG" -hide_banner -loglevel error -f lavfi -i "color=c=white:s=$size:r=1" -vf "$FILTER" -frames:v 1 -y "$out"
  local dim
  dim="$("$FFPROBE" -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$out")"
  [[ "$dim" == "1920x1080" ]] || fail "$name output is $dim instead of 1920x1080"
  local left right top bottom
  left="$(edge_avg "$out" 'crop=64:ih:0:0')"
  right="$(edge_avg "$out" 'crop=64:ih:iw-64:0')"
  top="$(edge_avg "$out" 'crop=iw:64:0:0')"
  bottom="$(edge_avg "$out" 'crop=iw:64:0:ih-64')"
  python3 - "$name" "$left" "$right" "$top" "$bottom" <<'PY'
import sys
name=sys.argv[1]
vals=[float(x) for x in sys.argv[2:]]
print(f"PASS: {name} edge YAVG = "+", ".join(f"{v:.1f}" for v in vals))
if min(vals) < 180:
    raise SystemExit(f"FAIL: {name} has a dark/black padded edge: {vals}")
PY
}

# These shapes would visibly letterbox/pillarbox with the old decrease+pad path.
check_frame square 1000x1000
check_frame portrait 900x1600
check_frame ultrawide 2400x800
pass 'square, portrait and ultrawide sources fill the full 16:9 frame without generated black bars'

echo 'ENDLUME 8.38 YouTube Fill 16:9 / No Black Bars gate passed.'
