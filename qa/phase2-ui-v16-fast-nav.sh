#!/bin/bash
set -Eeuo pipefail
V5="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
V8="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"
V11="$GITHUB_WORKSPACE/qa/phase2-ui-v11-full.sh"
P5="$RUNNER_TEMP/phase2-ui-v16-v5.sh"
P8="$RUNNER_TEMP/phase2-ui-v16-v8.sh"
P11="$RUNNER_TEMP/phase2-ui-v16-v11.sh"
python3 - "$V5" "$V8" "$V11" "$P5" "$P8" "$P11" <<'PY'
from pathlib import Path
import sys
v5=Path(sys.argv[1]).read_text()
v8=Path(sys.argv[2]).read_text()
v11=Path(sys.argv[3]).read_text()
old='$RUNNER_TEMP/endlume-phase2-v5-fixture'
new='$HOME/Desktop/ENDLUME_PHASE2_QA_${GITHUB_RUN_ID}'
if old not in v5: raise SystemExit('V16 FIX path missing')
v5=v5.replace(old,new,1)
repls={
"ui press 'Проект'; capture '01-project.png'":"capture '01-project.png'",
"ui press 'Рендер'; sleep .5; capture '07-render-idle.png'":"click_rel .81 .065; sleep .8; capture '07-render-idle.png'",
"ui press 'Библиотека'; sleep .5; capture '09-library.png'":"click_rel .87 .065; sleep .8; capture '09-library.png'",
"ui press 'Настройки'; sleep .5; ui press 'ОБЩИЕ'":"click_rel .955 .065; sleep .8; ui press 'ОБЩИЕ'",
"ui press 'Проект'; ui feature 'Эффект для каждого проекта' OFF":"click_rel .755 .065; sleep .8; ui feature 'Эффект для каждого проекта' OFF",
}
for a,b in repls.items():
    if a not in v5: raise SystemExit('V16 nav pattern missing: '+a)
    v5=v5.replace(a,b,1)
Path(sys.argv[4]).write_text(v5)
old8='BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"'
new8='BASE="$RUNNER_TEMP/phase2-ui-v16-v5.sh"'
if old8 not in v8: raise SystemExit('V16 V8 base missing')
v8=v8.replace(old8,new8,1)
Path(sys.argv[5]).write_text(v8)
old11='V8="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"'
new11='V8="$RUNNER_TEMP/phase2-ui-v16-v8.sh"'
if old11 not in v11: raise SystemExit('V16 V11 base missing')
v11=v11.replace(old11,new11,1)
Path(sys.argv[6]).write_text(v11)
PY
chmod +x "$P5" "$P8" "$P11"
echo "FAST_NAV=ENABLED"
exec bash "$P11"
