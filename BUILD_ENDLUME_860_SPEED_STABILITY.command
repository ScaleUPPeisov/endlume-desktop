#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_858_FINAL_INTEGRATED.command"
TMP="$(mktemp "$BASE_DIR/.endlume-860-speed-stability.XXXXXX.command")"
cleanup(){ rm -f "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
[[ -f "$BASE" ]] || { echo '❌ ENDLUME 8.60: 8.58 production builder missing' >&2; exit 1; }

python3 - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()

def once(old,new,label):
    global s
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'ENDLUME 8.60 builder: {label}: expected 1 anchor, found {n}')
    s=s.replace(old,new,1)

# Pin the exact source that passed the final physical 8.60 release gate.
once("src=src.replace(old_version,'EXPECTED_VERSION=\"1.0.0-alpha.8.58\"',1)",
     "src=src.replace(old_version,'EXPECTED_VERSION=\"1.0.0-alpha.8.60\"',1)",
     'version pin')
once("src=src.replace(old_pin,'PINNED_SHA=\"abdbe27a73be6a17d9d409599971cc3ef15840c9\"',1)",
     "src=src.replace(old_pin,'PINNED_SHA=\"b710f67090a0eebc9a87eeb45c5e52078b37a7a3\"',1)",
     'source pin')

# Carry 8.60 runtime migration after the already-certified 8.56/8.57/8.58 stack.
old="src=src.replace(cd_anchor,cd_anchor+'python3 scripts/apply-render-isolation-8-56.py\\npython3 scripts/apply-master-frame-hotfix-8-57.py\\npython3 scripts/apply-queue-finalization-hotfix-8-58.py\\n',1)"
new="src=src.replace(cd_anchor,cd_anchor+'python3 scripts/apply-render-isolation-8-56.py\\npython3 scripts/apply-master-frame-hotfix-8-57.py\\npython3 scripts/apply-queue-finalization-hotfix-8-58.py\\npython3 scripts/apply-render-speed-stability-8-60.py\\n',1)"
once(old,new,'8.60 migration insertion')

# Production contract assertions must validate the effective 8.60 package identity.
s=s.replace("1.0.0-alpha.8.58","1.0.0-alpha.8.60")
s=s.replace(r"1\.0\.0-alpha\.8\.58",r"1\.0\.0-alpha\.8\.60")

# Add narrow 8.60 guards without changing the existing media/queue/VYRON gates.
anchor="# Original approved icon: transparent cyan/violet/magenta infinity, no black rounded square."
extra=r'''# 8.60 speed stability + protected equalizer + in-place manifest.
grep -Fq 'strict-860-base.png' src-tauri/src/render.rs || fail "8.60 strict static-base optimization missing"
grep -Fq 'periodic-860-base.png' src-tauri/src/render.rs || fail "8.60 periodic static-base optimization missing"
grep -Fq '"-filter_complex_threads","8"' src-tauri/src/render.rs || fail "8-thread strict filter contract missing"
grep -Fq 'expand_video_prefix_cycle(&seed,&seed' src-tauri/src/render.rs || fail "8.60 in-place manifest dispatch missing"
grep -Fq 'fn chromakey_params_859' src-tauri/src/cache.rs || fail "protected round equalizer helper missing"
grep -Fq 'strict-860|' src-tauri/src/cache.rs || fail "8.60 strict Effects cache fingerprint missing"
'''
if anchor not in s:
    raise SystemExit('ENDLUME 8.60 builder: guard insertion anchor missing')
s=s.replace(anchor,extra+anchor,1)

# Re-run the dedicated static contract test in the exact production source.
needle='node scripts/test-queue-finalization-8-58.mjs "$SRC/.queue-test-dist/queue-state.js"\nnpm run build\n'
replacement='node scripts/test-queue-finalization-8-58.mjs "$SRC/.queue-test-dist/queue-state.js"\npython3 scripts/test-render-speed-stability-8-60.py "$SRC"\nnpm run build\n'
once(needle,replacement,'8.60 regression insertion')

s=s.replace('ENDLUME STUDIO 8.58 final integrated source built and signed','ENDLUME STUDIO 8.60 render-speed-stability source built and signed')
s=s.replace('queue 40/40 + VYRON Render/channel + 3381/3381 integrity + whole-track MP3 + 500-700 MB + zero-copy gates passed','queue 40/40 + VYRON + bright equalizer + sustained <=30s strict masters + Subscribe OFF/ON + whole-track MP3 + 500-700 MB + in-place manifest gates passed')
Path(sys.argv[2]).write_text(s)
PY

chmod +x "$TMP"
/bin/bash "$TMP"
