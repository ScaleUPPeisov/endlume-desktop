#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v28-features-no-whose.sh"
OUT="$RUNNER_TEMP/phase2-ui-v29-runtime.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
old=""" if(cmd==='feature'){const l=label(a1),sm=scrollVisible(l);let q=near(l,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']),on=q.name==='ВЫКЛЮЧИТЬ',want=a2==='ON';if(on!==want){q.e.click();delay(.45);q=near(l,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']);}const state=q.name==='ВЫКЛЮЧИТЬ'?'ON':'OFF';if(state!==a2)throw new Error('feature state mismatch '+a1+' got '+state);return `FEATURE=${a1}|STATE=${state}|SCROLL=${sm}|LABEL_Y=${box(l).y}|BUTTON_Y=${box(q.e).y}`;}"""
new=""" if(cmd==='featureOff'||cmd==='featureOn'){const l=label(a1),sm=scrollVisible(l);let q=near(l,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']),on=q.name==='ВЫКЛЮЧИТЬ',want=cmd==='featureOn';if(on!==want){q.e.click();delay(.45);q=near(l,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']);}const state=q.name==='ВЫКЛЮЧИТЬ'?'ON':'OFF',expected=want?'ON':'OFF';if(state!==expected)throw new Error('feature state mismatch '+a1+' expected '+expected+' got '+state);return `FEATURE=${a1}|STATE=${state}|SCROLL=${sm}|LABEL_Y=${box(l).y}|BUTTON_Y=${box(q.e).y}`;}"""
if old not in s: raise SystemExit('V29 feature block not found')
s=s.replace(old,new,1)
repls={
"u28 feature 'Эффект для каждого проекта' OFF":"u28 featureOff 'Эффект для каждого проекта'",
"u28 feature 'Эффект для каждого проекта' ON":"u28 featureOn 'Эффект для каждого проекта'",
"u28 feature 'Subscribe Button' OFF":"u28 featureOff 'Subscribe Button'",
"u28 feature 'Subscribe Button' ON":"u28 featureOn 'Subscribe Button'",
}
for a,b in repls.items():
    if a not in s: raise SystemExit('V29 call not found: '+a)
    s=s.replace(a,b,1)
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$OUT"
exec bash "$OUT"
