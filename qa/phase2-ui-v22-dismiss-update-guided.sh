#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v21-owner-guided.sh"
OUT="$RUNNER_TEMP/phase2-ui-v22-wrapper.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
needle="""echo LICENSED_SESSION=PASS

GUIDE=\"$HOME/Desktop/ENDLUME_PHASE2_QA_GUIDED\"
"""
insert=r'''echo LICENSED_SESSION=PASS

cat > "$REPORT/dismiss-update-v22.js" <<'JXA'
function run(argv){
  const pid=Number(argv[0]),se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();
  if(ps.length!==1)throw new Error('candidate missing');const p=ps[0];p.frontmost=true;
  const str=f=>{try{const v=f();return v==null?'':String(v)}catch(_){return ''}};
  function scan(){let ws=p.windows(),q=[],seen=0;for(let i=0;i<ws.length;i++)q.push(ws[i]);while(q.length&&seen<650){const e=q.shift();seen++;const role=str(()=>e.role()),name=str(()=>e.name()),desc=str(()=>e.description()),text=name+' '+desc;if(role==='AXButton'&&(name==='ПОЗЖЕ'||desc==='ПОЗЖЕ'||name==='Later'||desc==='Later'))return {kind:'button',e};if(text.includes('Доступно обновление'))var overlay=true;let kids=[];try{kids=e.uiElements()}catch(_){};for(let j=0;j<kids.length;j++)q.push(kids[j]);}return {kind:overlay?'overlay':'none'};}
  for(let n=0;n<12;n++){const r=scan();if(r.kind==='button'){r.e.click();delay(.8);const after=scan();if(after.kind!=='overlay'&&after.kind!=='button')return 'UPDATE_OVERLAY_DISMISSED';}else if(r.kind==='none'){return 'NO_UPDATE_OVERLAY';}delay(.5);}return 'UPDATE_OVERLAY_STILL_PRESENT';
}
JXA
set +e
DISMISS_OUT=$(/usr/bin/osascript -l JavaScript "$REPORT/dismiss-update-v22.js" "$PID" 2>"$REPORT/dismiss-update-v22.err")
DISMISS_RC=$?
set -e
printf 'UPDATE_DISMISS_RC=%s\nUPDATE_DISMISS_RESULT=%s\n' "$DISMISS_RC" "${DISMISS_OUT:-EMPTY}" > "$REPORT/update-dismiss-v22.txt"
if [ "$DISMISS_RC" -ne 0 ] || [ "${DISMISS_OUT:-}" = "UPDATE_OVERLAY_STILL_PRESENT" ]; then
  echo "UPDATE_OVERLAY_BLOCKED=${DISMISS_OUT:-RC_$DISMISS_RC}" >&2
  exit 96
fi
sleep 1

GUIDE="$HOME/Desktop/ENDLUME_PHASE2_QA_GUIDED"
'''
if needle not in s:
    raise SystemExit('V22 insertion point missing')
s=s.replace(needle,insert,1)
s=s.replace('OWNER_GUIDED_V21_CAPTURE=PASS','OWNER_GUIDED_V22_CAPTURE=PASS')
s=s.replace('owner-guided-v21.txt','owner-guided-v22.txt')
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$OUT"
exec bash "$OUT"
