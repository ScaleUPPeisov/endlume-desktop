#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_860_SPEED_STABILITY.command"
TMP="$(mktemp "$BASE_DIR/.endlume-861-external-stability.XXXXXX.command")"
cleanup(){ rm -f "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
[[ -f "$BASE" ]] || { echo '❌ ENDLUME 8.61: 8.60 production builder missing' >&2; exit 1; }

python3 - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()

def require_once(old,label):
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'ENDLUME 8.61 builder: {label}: expected 1 anchor, found {n}')

def once(old,new,label):
    global s
    require_once(old,label)
    s=s.replace(old,new,1)

# Exact source used by the final idle/persistent-cache M1 speed gate.
once('b710f67090a0eebc9a87eeb45c5e52078b37a7a3','4ec332f4ccc4bca511065d8276e1ab34ac255826','source pin')
s=s.replace('1.0.0-alpha.8.60','1.0.0-alpha.8.61')
s=s.replace(r'1\.0\.0-alpha\.8\.60',r'1\.0\.0-alpha\.8\.61')

# Apply the 8.61 local-scratch migration after the certified 8.60 stack.
needle=r'python3 scripts/apply-render-speed-stability-8-60.py\n'
if needle not in s:
    raise SystemExit('ENDLUME 8.61 builder: 8.60 migration anchor missing')
s=s.replace(needle,needle+r'python3 scripts/apply-local-scratch-stability-8-61-v2.py\n',1)

# 8.61 invariants: all heavy temporary master/audio/manifest work is local to the Mac;
# only the completed MOV is finalized to the requested external output directory.
anchor='# Original approved icon: transparent cyan/violet/magenta infinity, no black rounded square.'
extra=r'''# 8.61 external-disk stability.
grep -Fq 'fn render_work_dir(app:&AppHandle' src-tauri/src/render.rs || fail "8.61 local render scratch missing"
grep -Fq 'app.path().app_cache_dir()' src-tauri/src/render.rs || fail "8.61 app-cache scratch missing"
grep -Fq 'let root=base.join("render-work")' src-tauri/src/render.rs || fail "8.61 render-work root missing"
grep -Fq 'fn finalize_local_output(src:&Path,out:&Path)' src-tauri/src/render.rs || fail "8.61 single external finalize missing"
grep -Fq 'std::io::copy(&mut input,&mut output)' src-tauri/src/render.rs || fail "8.61 cross-volume final copy missing"
grep -Fq 'finalize_local_output(&seed,out)' src-tauri/src/render.rs || fail "8.61 zero-copy final dispatch missing"
! grep -Fq 'let root=output.join(".ENDLUME-work")' src-tauri/src/render.rs || fail "8.61 external work-dir regression"
'''
if anchor not in s:
    raise SystemExit('ENDLUME 8.61 builder: guard insertion anchor missing')
s=s.replace(anchor,extra+anchor,1)

# Re-run the dedicated 8.61 source contract test in the exact package source.
needle=r'python3 scripts/test-render-speed-stability-8-60.py "$SRC"\n'
if needle not in s:
    raise SystemExit('ENDLUME 8.61 builder: 8.60 regression anchor missing')
s=s.replace(needle,needle+r'python3 scripts/test-local-scratch-stability-8-61.py "$SRC"\n',1)

s=s.replace('ENDLUME STUDIO 8.60 render-speed-stability source built and signed','ENDLUME STUDIO 8.61 external-disk-stability source built and signed')
s=s.replace('queue 40/40 + VYRON + bright equalizer + sustained <=30s strict masters + Subscribe OFF/ON + whole-track MP3 + 500-700 MB + in-place manifest gates passed','queue 40/40 + VYRON + bright equalizer + local Mac render scratch + single external final write + whole-track MP3 + 500-700 MB + in-place manifest gates passed')
Path(sys.argv[2]).write_text(s)
PY

chmod +x "$TMP"
/bin/bash "$TMP"
