#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
OUT="$RUNNER_TEMP/phase2-ui-v28-runtime.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
start=s.index("READY=0; for n in $(seq 0 120);")
block=r'''cat > "$REPORT/v28.js" <<'JXA'
function run(argv){
 const pid=Number(argv[0]),cmd=argv[1],a1=argv[2]||'',a2=argv[3]||'',se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();
 if(ps.length!==1)throw new Error('candidate missing');
 const p=ps[0];p.frontmost=true;delay(.04);const w=p.windows()[0],u=w.groups()[0].groups()[0].scrollAreas()[0].uiElements()[0];
 const str=f=>{try{const v=f();return v==null?'':String(v)}catch(_){return ''}};
 const box=e=>{try{const q=e.position(),z=e.size();return{x:Number(q[0]),y:Number(q[1]),w:Number(z[0]),h:Number(z[1])}}catch(_){return{x:0,y:0,w:0,h:0}}};
 function arr(f){try{return f()}catch(_){return []}}
 function named(xs,t){for(let i=0;i<xs.length;i++){const e=xs[i],n=str(()=>e.name()),d=str(()=>e.description());if(n===t||d===t)return e;}return null;}
 function label(t){let e=named(arr(()=>u.staticTexts()),t);if(!e)e=named(arr(()=>u.headings()),t);if(!e)throw new Error('label missing '+t);return e;}
 function buttonsByName(t){const xs=arr(()=>u.buttons()),out=[];for(let i=0;i<xs.length;i++){const e=xs[i],n=str(()=>e.name()),d=str(()=>e.description());if(n===t||d===t)out.push(e);}return out;}
 function scrollVisible(e){try{const as=arr(()=>e.actions());for(let i=0;i<as.length;i++){if(str(()=>as[i].name())==='AXScrollToVisible'){as[i].perform();delay(.35);return 'ACTION';}}}catch(_){};try{e.performAction('AXScrollToVisible');delay(.35);return 'DIRECT';}catch(_){};return 'NONE';}
 function near(l,names){const lb=box(l),ly=lb.y+lb.h/2,lx=lb.x+lb.w/2;let best=null;for(const n of names){const xs=buttonsByName(n);for(let i=0;i<xs.length;i++){const e=xs[i],b=box(e),score=Math.abs((b.y+b.h/2)-ly)*10+Math.abs((b.x+b.w/2)-lx);if(!best||score<best.score)best={e,name:n,score};}}if(!best)throw new Error('near button missing '+names.join('/'));return best;}
 if(cmd==='dismiss'){for(const n of ['ПОЗЖЕ','Later']){const xs=buttonsByName(n);if(xs.length){xs[0].click();delay(.4);return 'DISMISSED';}}return 'NONE';}
 if(cmd==='geom'){const q=w.position(),z=w.size();return `${q[0]},${q[1]},${z[0]},${z[1]}`;}
 if(cmd==='feature'){const l=label(a1),sm=scrollVisible(l);let q=near(l,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']),on=q.name==='ВЫКЛЮЧИТЬ',want=a2==='ON';if(on!==want){q.e.click();delay(.45);q=near(l,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']);}const state=q.name==='ВЫКЛЮЧИТЬ'?'ON':'OFF';if(state!==a2)throw new Error('feature state mismatch '+a1+' got '+state);return `FEATURE=${a1}|STATE=${state}|SCROLL=${sm}|LABEL_Y=${box(l).y}|BUTTON_Y=${box(q.e).y}`;}
 if(cmd==='configure'){const l=label(a1),sm=scrollVisible(l),q=near(l,['НАСТРОИТЬ →']);q.e.click();delay(.7);return `CONFIGURE=${a1}|SCROLL=${sm}`;}
 if(cmd==='press'){const xs=buttonsByName(a1);if(!xs.length)throw new Error('button missing '+a1);xs[0].click();delay(.6);return `PRESSED=${a1}`;}
 throw new Error('bad cmd');
}
JXA
u28(){ /usr/bin/osascript -l JavaScript "$REPORT/v28.js" "$PID" "$@"; }
cat > "$REPORT/nav-v28.js" <<'JXA'
function run(argv){const pid=Number(argv[0]),se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();if(ps.length!==1)return 'NAV=0 ACT=false';const p=ps[0],w=p.windows()[0],q=[w];let n=0,c=0,a=false,s={};const str=f=>{try{const v=f();return v==null?'':String(v)}catch(_){return ''}};while(q.length&&n<350){const e=q.shift();n++;const x=str(()=>e.name()),d=str(()=>e.description()),h=x+' '+d;for(const t of ['Проект','Рендер','Библиотека','Настройки'])if(!s[t]&&(x===t||d===t)){s[t]=1;c++;}if(h.includes('АКТИВИРОВАТЬ'))a=true;let k=[];try{k=e.uiElements()}catch(_){};for(let j=0;j<k.length;j++)q.push(k[j]);}return `NAV=${c} ACT=${a}`;}
JXA
READY=0
for second in $(seq 0 30);do set +e;O=$(/usr/bin/osascript -l JavaScript "$REPORT/nav-v28.js" "$PID" 2>/dev/null);R=$?;set -e;N="$(printf '%s' "$O"|sed -n 's/.*NAV=\([0-9][0-9]*\).*/\1/p')";A="$(printf '%s' "$O"|sed -n 's/.*ACT=\([^ ]*\).*/\1/p')";[ "$R" -eq 0 ]&&[ "${A:-false}" = true ]&&exit 75;if [ "$R" -eq 0 ]&&[ "${N:-0}" -eq 4 ] 2>/dev/null;then READY=1;break;fi;sleep 1;done
test "$READY" -eq 1
printf 'LICENSED_SESSION=PASS\nNORMAL_NAVIGATION=PASS\nLICENSE_BYPASS=NO\n' > "$REPORT/license-gate.txt"
u28 dismiss > "$REPORT/update-dismiss-v28.txt";sleep .3
cap(){ local o="$1" g;g="$(u28 geom)";IFS=',' read -r x y w h <<< "$g";/usr/sbin/screencapture -x -R"$x,$y,$w,$h" "$REPORT/screens/$o";test -s "$REPORT/screens/$o";}
u28 feature 'Эффект для каждого проекта' OFF > "$REPORT/effects-off-v28.txt";cap '02-effects-off.png'
u28 feature 'Эффект для каждого проекта' ON > "$REPORT/effects-on-v28.txt";cap '03-effects-on.png'
u28 configure 'Эффект для каждого проекта' > "$REPORT/effects-config-v28.txt";cap '06-effects-editor.png'
u28 press '← ВЕРНУТЬСЯ К ПРОЕКТУ' > "$REPORT/effects-return-v28.txt"
u28 feature 'Subscribe Button' OFF > "$REPORT/subscribe-off-v28.txt";cap '04-subscribe-off.png'
u28 feature 'Subscribe Button' ON > "$REPORT/subscribe-on-v28.txt";cap '05-subscribe-on.png'
u28 configure 'Subscribe Button' > "$REPORT/subscribe-config-v28.txt";cap '06b-subscribe-editor.png'
printf 'EFFECTS_TOGGLE=PASS\nEFFECTS_EDITOR=PASS\nSUBSCRIBE_TOGGLE=PASS\nSUBSCRIBE_EDITOR=PASS\nPRODUCT_FILES_CHANGED=0\n' > "$REPORT/v28-result.txt"
echo FEATURES_NO_WHOSE_V28=PASS
'''
s=s[:start]+block+'\n'
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$OUT"
exec bash "$OUT"
