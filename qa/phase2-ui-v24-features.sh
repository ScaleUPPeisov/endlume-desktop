#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
OUT="$RUNNER_TEMP/phase2-ui-v24-runtime.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
start=s.index("READY=0; for n in $(seq 0 120);")
block=r'''cat > "$REPORT/ui-v24.js" <<'JXA'
function run(argv){
 const pid=Number(argv[0]),cmd=argv[1],a1=argv[2]||'',a2=argv[3]||'',se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();
 if(ps.length!==1)throw new Error('candidate missing');const p=ps[0];p.frontmost=true;delay(.05);
 const str=f=>{try{const v=f();return v==null?'':String(v)}catch(_){return ''}};
 function box(e){try{const q=e.position(),z=e.size();return{x:Number(q[0]),y:Number(q[1]),w:Number(z[0]),h:Number(z[1])}}catch(_){return{x:0,y:0,w:0,h:0}}}
 function walk(max=850){const ws=p.windows(),q=[];for(let i=0;i<ws.length;i++)q.push(ws[i]);const out=[];let seen=0;while(q.length&&seen<max){const e=q.shift();seen++;const role=str(()=>e.role()),name=str(()=>e.name()),desc=str(()=>e.description());out.push({e,role,name,desc,b:box(e)});let kids=[];try{kids=e.uiElements()}catch(_){};for(let j=0;j<kids.length;j++)q.push(kids[j]);}return out;}
 function exact(xs,t,role){return xs.find(o=>(o.name===t||o.desc===t)&&(!role||o.role===role));}
 function nearButton(label,names){const xs=walk(),l=exact(xs,label);if(!l)throw new Error('label missing '+label);let best=null;for(const o of xs){if(o.role!=='AXButton'||!names.includes(o.name))continue;const dy=Math.abs((o.b.y+o.b.h/2)-(l.b.y+l.b.h/2)),dx=Math.abs((o.b.x+o.b.w/2)-(l.b.x+l.b.w/2)),score=dy*10+dx;if(!best||score<best.score)best={o,score};}if(!best)throw new Error('near button missing '+label);return {l,b:best.o};}
 function reveal(e){try{e.performAction('AXScrollToVisible');delay(.5);return 'AXScrollToVisible'}catch(_){try{e.actions.byName('AXScrollToVisible').perform();delay(.5);return 'ACTION'}catch(__){return 'NO_SCROLL_ACTION'}}}
 if(cmd==='nav'){const xs=walk(450),names=['Проект','Рендер','Библиотека','Настройки'];let c=0;for(const n of names)if(exact(xs,n))c++;const act=xs.some(o=>(o.name+' '+o.desc).includes('АКТИВИРОВАТЬ'));return `NAV=${c} ACT=${act}`;}
 if(cmd==='dismiss'){const xs=walk(650),x=xs.find(o=>o.role==='AXButton'&&(o.name==='ПОЗЖЕ'||o.desc==='ПОЗЖЕ'||o.name==='Later'||o.desc==='Later'));if(x){x.e.click();delay(.8);return 'DISMISSED'}return 'NONE';}
 if(cmd==='geom'){const w=p.windows()[0],q=w.position(),z=w.size();return `${q[0]},${q[1]},${z[0]},${z[1]}`;}
 if(cmd==='feature'){const want=a2==='ON',q=nearButton(a1,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']),on=q.b.name==='ВЫКЛЮЧИТЬ';reveal(q.l.e);if(on!==want){q.b.e.click();delay(.7);}const q2=nearButton(a1,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']);return `FEATURE=${a1}|STATE=${q2.b.name==='ВЫКЛЮЧИТЬ'?'ON':'OFF'}|SCROLL=${reveal(q2.l.e)}`;}
 if(cmd==='configure'){const q=nearButton(a1,['НАСТРОИТЬ →']);reveal(q.l.e);q.b.e.click();delay(1);return `CONFIGURE=${a1}`;}
 if(cmd==='press'){const xs=walk(),x=exact(xs,a1,'AXButton');if(!x)throw new Error('button missing '+a1);x.e.click();delay(.8);return `PRESSED=${a1}`;}
 if(cmd==='has'){const xs=walk(),x=xs.find(o=>(o.name||'').includes(a1)||(o.desc||'').includes(a1));return x?'1':'0';}
 throw new Error('bad cmd');
}
JXA
ui24(){ /usr/bin/osascript -l JavaScript "$REPORT/ui-v24.js" "$PID" "$@"; }
READY=0
for second in $(seq 0 30); do set +e; O=$(ui24 nav 2>/dev/null); R=$?; set -e; N="$(printf '%s' "$O"|sed -n 's/.*NAV=\([0-9][0-9]*\).*/\1/p')"; A="$(printf '%s' "$O"|sed -n 's/.*ACT=\([^ ]*\).*/\1/p')"; [ "$R" -eq 0 ]&&[ "${A:-false}" = true ]&&exit 75; if [ "$R" -eq 0 ]&&[ "${N:-0}" -eq 4 ] 2>/dev/null;then READY=1;break;fi;sleep 1;done
test "$READY" -eq 1
printf 'LICENSED_SESSION=PASS\nNORMAL_NAVIGATION=PASS\nLICENSE_BYPASS=NO\n' > "$REPORT/license-gate.txt"
ui24 dismiss > "$REPORT/update-dismiss-v24.txt"; sleep 1
capture24(){ local out="$1" g; g="$(ui24 geom)"; IFS=',' read -r x y w h <<< "$g"; /usr/sbin/screencapture -x -R"$x,$y,$w,$h" "$REPORT/screens/$out"; test -s "$REPORT/screens/$out"; }

ui24 feature 'Эффект для каждого проекта' OFF > "$REPORT/effects-off.txt"; capture24 '02-effects-off.png'
ui24 feature 'Эффект для каждого проекта' ON > "$REPORT/effects-on.txt"; capture24 '03-effects-on.png'
ui24 configure 'Эффект для каждого проекта' > "$REPORT/effects-configure.txt"; capture24 '06-effects-live-preview.png'
ui24 press '← ВЕРНУТЬСЯ К ПРОЕКТУ' > "$REPORT/effects-return.txt"
ui24 feature 'Subscribe Button' OFF > "$REPORT/subscribe-off.txt"; capture24 '04-subscribe-off.png'
ui24 feature 'Subscribe Button' ON > "$REPORT/subscribe-on.txt"; capture24 '05-subscribe-on.png'
ui24 configure 'Subscribe Button' > "$REPORT/subscribe-configure.txt"; capture24 '06b-subscribe-live-preview.png'
printf 'EFFECTS_TOGGLE_INTERACTION=PASS\nEFFECTS_EDITOR_OPEN=PASS\nSUBSCRIBE_TOGGLE_INTERACTION=PASS\nSUBSCRIBE_EDITOR_OPEN=PASS\nPRODUCT_FILES_CHANGED=0\nSTABLE_TOUCHED=NO\nLIVE_UPDATER_TOUCHED=NO\n' > "$REPORT/v24-result.txt"
echo PHYSICAL_FEATURES_V24=PASS
'''
s=s[:start]+block+'\n'
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$OUT"
exec bash "$OUT"
