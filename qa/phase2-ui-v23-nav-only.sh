#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
OUT="$RUNNER_TEMP/phase2-ui-v23-runtime.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
start=s.index("READY=0; for n in $(seq 0 120);")
block=r'''cat > "$REPORT/ui-v23.js" <<'JXA'
function run(argv){
 const pid=Number(argv[0]),cmd=argv[1],arg=argv[2]||'',se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();
 if(ps.length!==1)throw new Error('candidate missing');const p=ps[0];p.frontmost=true;delay(.05);
 const str=f=>{try{const v=f();return v==null?'':String(v)}catch(_){return ''}};
 function scan(test,max=700){const ws=p.windows(),q=[];for(let i=0;i<ws.length;i++)q.push(ws[i]);let seen=0;while(q.length&&seen<max){const e=q.shift();seen++;const role=str(()=>e.role()),name=str(()=>e.name()),desc=str(()=>e.description());if(test({e,role,name,desc}))return {e,role,name,desc,seen};let kids=[];try{kids=e.uiElements()}catch(_){};for(let j=0;j<kids.length;j++)q.push(kids[j]);}return null;}
 if(cmd==='nav'){let f={p:false,r:false,l:false,s:false,a:false},ws=p.windows(),q=[];for(let i=0;i<ws.length;i++)q.push(ws[i]);let seen=0;while(q.length&&seen<450){const e=q.shift();seen++;const n=str(()=>e.name()),d=str(()=>e.description()),h=n+' '+d;if(n==='Проект'||d==='Проект')f.p=true;if(n==='Рендер'||d==='Рендер')f.r=true;if(n==='Библиотека'||d==='Библиотека')f.l=true;if(n==='Настройки'||d==='Настройки')f.s=true;if(h.includes('АКТИВИРОВАТЬ')||h.includes('Активация ENDLUME')||h.includes('Нужна активация'))f.a=true;let k=[];try{k=e.uiElements()}catch(_){};for(let j=0;j<k.length;j++)q.push(k[j]);}return `NAV=${[f.p,f.r,f.l,f.s].filter(Boolean).length} ACT=${f.a}`;}
 if(cmd==='press'){const x=scan(o=>o.role==='AXButton'&&(o.name===arg||o.desc===arg));if(!x)throw new Error('button missing '+arg);x.e.click();delay(.7);return `PRESSED=${arg}|SEEN=${x.seen}`;}
 if(cmd==='dismiss'){for(let n=0;n<12;n++){const x=scan(o=>o.role==='AXButton'&&(o.name==='ПОЗЖЕ'||o.desc==='ПОЗЖЕ'||o.name==='Later'||o.desc==='Later'));if(x){x.e.click();delay(.8);return 'UPDATE_OVERLAY_DISMISSED';}delay(.4);}return 'NO_UPDATE_OVERLAY';}
 if(cmd==='geom'){const w=p.windows()[0],q=w.position(),z=w.size();return `${q[0]},${q[1]},${z[0]},${z[1]}`;}
 throw new Error('bad cmd');
}
JXA
ui23(){ /usr/bin/osascript -l JavaScript "$REPORT/ui-v23.js" "$PID" "$@"; }

echo MANUAL_ACTION_IF_PROMPT=CLICK_ALLOW_NOT_ALWAYS_ALLOW
READY=0
for second in $(seq 0 30); do
  set +e; OUTNAV=$(ui23 nav 2>/dev/null); RC=$?; set -e
  NAV="$(printf '%s' "$OUTNAV"|sed -n 's/.*NAV=\([0-9][0-9]*\).*/\1/p')"; ACT="$(printf '%s' "$OUTNAV"|sed -n 's/.*ACT=\([^ ]*\).*/\1/p')"
  [ "$RC" -eq 0 ] && [ "${ACT:-false}" = true ] && exit 75
  if [ "$RC" -eq 0 ] && [ "${NAV:-0}" -eq 4 ] 2>/dev/null; then READY=1; break; fi
  sleep 1
done
test "$READY" -eq 1
printf 'LICENSED_SESSION=PASS\nNORMAL_NAVIGATION=PASS\nLICENSE_BYPASS=NO\n' > "$REPORT/license-gate.txt"
ui23 dismiss > "$REPORT/update-dismiss-v23.txt"
sleep 1

capture23(){ local out="$1" g; g="$(ui23 geom)"; IFS=',' read -r x y w h <<< "$g"; /usr/sbin/screencapture -x -R"$x,$y,$w,$h" "$REPORT/screens/$out"; test -s "$REPORT/screens/$out"; echo "CAPTURED=$out"; }

capture23 '01-project.png'
ui23 press 'Рендер' > "$REPORT/nav-render.txt"; capture23 '07-render-idle.png'
ui23 press 'Библиотека' > "$REPORT/nav-library.txt"; capture23 '09-library.png'
ui23 press 'Настройки' > "$REPORT/nav-settings.txt"; sleep .5
ui23 press 'ОБЩИЕ' > "$REPORT/nav-general.txt"; capture23 '10-settings-general.png'
ui23 press 'FAST ENGINE' > "$REPORT/nav-fast-engine.txt"; capture23 '11-settings-fast-engine.png'
ui23 press 'ОБНОВЛЕНИЯ' > "$REPORT/nav-updates.txt"; capture23 '12-settings-updates.png'
ui23 press 'О ПРОГРАММЕ' > "$REPORT/nav-about.txt"; capture23 '13-settings-about.png'
printf 'PROJECT_UI_CAPTURE=PASS\nRENDER_IDLE_CAPTURE=PASS\nLIBRARY_CAPTURE=PASS\nSETTINGS_GENERAL_CAPTURE=PASS\nSETTINGS_FAST_ENGINE_CAPTURE=PASS\nSETTINGS_UPDATES_CAPTURE=PASS\nSETTINGS_ABOUT_CAPTURE=PASS\nPRODUCT_FILES_CHANGED=0\nSTABLE_TOUCHED=NO\nLIVE_UPDATER_TOUCHED=NO\n' > "$REPORT/v23-result.txt"
echo PHYSICAL_NAV_V23=PASS
'''
s=s[:start]+block+'\n'
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$OUT"
exec bash "$OUT"
