#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_858_FINAL_INTEGRATED.command"
TMP="$(mktemp "$BASE_DIR/.endlume-861-external-stability.XXXXXX.command")"
cleanup(){ rm -f "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
[[ -f "$BASE" ]] || { echo '❌ ENDLUME 8.61: 8.58 production builder missing' >&2; exit 1; }

python3 - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()

def once(old,new,label):
    global s
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'ENDLUME 8.61 builder: {label}: expected 1 anchor, found {n}')
    s=s.replace(old,new,1)

# Pin the exact candidate source used by the final idle/persistent-cache M1 gate.
once("src=src.replace(old_version,'EXPECTED_VERSION=\"1.0.0-alpha.8.58\"',1)",
     "src=src.replace(old_version,'EXPECTED_VERSION=\"1.0.0-alpha.8.61\"',1)",
     'version pin')
once("src=src.replace(old_pin,'PINNED_SHA=\"abdbe27a73be6a17d9d409599971cc3ef15840c9\"',1)",
     "src=src.replace(old_pin,'PINNED_SHA=\"4ec332f4ccc4bca511065d8276e1ab34ac255826\"',1)",
     'source pin')

# Build the certified 8.58 stack, then apply the 8.60 speed/equalizer migration and
# the 8.61 local-Mac scratch / single external final-write migration.
old="src=src.replace(cd_anchor,cd_anchor+'python3 scripts/apply-render-isolation-8-56.py\\npython3 scripts/apply-master-frame-hotfix-8-57.py\\npython3 scripts/apply-queue-finalization-hotfix-8-58.py\\n',1)"
new="src=src.replace(cd_anchor,cd_anchor+'python3 scripts/apply-render-isolation-8-56.py\\npython3 scripts/apply-master-frame-hotfix-8-57.py\\npython3 scripts/apply-queue-finalization-hotfix-8-58.py\\npython3 scripts/apply-render-speed-stability-8-60.py\\npython3 scripts/apply-local-scratch-stability-8-61-v2.py\\n',1)"
once(old,new,'8.60/8.61 migration insertion')

# Production package identity is 8.61.
s=s.replace('1.0.0-alpha.8.58','1.0.0-alpha.8.61')
s=s.replace(r'1\.0\.0-alpha\.8\.58',r'1\.0\.0-alpha\.8\.61')

# Add narrow 8.60 + 8.61 guards without changing the proven media/queue/VYRON gates.
anchor="# Original approved icon: transparent cyan/violet/magenta infinity, no black rounded square."
extra=r'''# 8.60 speed/equalizer/in-place-manifest contracts.
grep -Fq 'strict-860-base.png' src-tauri/src/render.rs || fail "8.60 strict static-base optimization missing"
grep -Fq 'periodic-860-base.png' src-tauri/src/render.rs || fail "8.60 periodic static-base optimization missing"
grep -Fq '"-filter_complex_threads","8"' src-tauri/src/render.rs || fail "8-thread strict filter contract missing"
grep -Fq 'expand_video_prefix_cycle(&seed,&seed' src-tauri/src/render.rs || fail "8.60 in-place manifest dispatch missing"
grep -Fq 'fn chromakey_params_859' src-tauri/src/cache.rs || fail "protected round equalizer helper missing"
grep -Fq 'strict-860|' src-tauri/src/cache.rs || fail "8.60 strict Effects cache fingerprint missing"
# 8.61 external-disk stability contracts.
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

# Re-run the dedicated 8.60 and 8.61 static contracts in the exact production source.
needle='node scripts/test-queue-finalization-8-58.mjs "$SRC/.queue-test-dist/queue-state.js"\nnpm run build\n'
replacement='node scripts/test-queue-finalization-8-58.mjs "$SRC/.queue-test-dist/queue-state.js"\npython3 scripts/test-render-speed-stability-8-60.py "$SRC"\npython3 scripts/test-local-scratch-stability-8-61.py "$SRC"\nnpm run build\n'
once(needle,replacement,'8.60/8.61 regression insertion')

s=s.replace('ENDLUME STUDIO 8.58 final integrated source built and signed','ENDLUME STUDIO 8.61 external-disk-stability source built and signed')
s=s.replace('queue 40/40 + VYRON Render/channel + 3381/3381 integrity + whole-track MP3 + 500-700 MB + zero-copy gates passed','queue 40/40 + VYRON + bright equalizer + local Mac render scratch + single external final write + whole-track MP3 + 500-700 MB + in-place manifest gates passed')
Path(sys.argv[2]).write_text(s)
PY

chmod +x "$TMP"
/bin/bash "$TMP"
