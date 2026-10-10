#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"
OUT="$RUNNER_TEMP/phase2-ui-v9-wrapper.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
old=r'''# Scroll to project bottom; output picker sits above fixed queue footer.
/usr/bin/osascript -e 'tell application "System Events" to key code 125 using {command down}'
sleep .4
click_rel .50 .72
choose_safe "$FIX/output"
sleep 1
'''
new=r'''cat > "$REPORT/ui-direct-v9.js" <<'JXA'
function run(argv){
  const pid=Number(argv[0]),cmd=argv[1],a1=argv[2]||'',a2=argv[3]||'';
  const se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();if(ps.length!==1)throw new Error('candidate missing');
  const p=ps[0];p.frontmost=true;delay(.05);const ws=p.windows();if(!ws.length)throw new Error('no window');const w=ws[0];
  const safe=f=>{try{return f()}catch(_){return []}},str=f=>{try{const v=f();return v==null?'':String(v)}catch(_){return ''}};
  function root(){const g1=safe(()=>w.groups())[0],g2=g1&&safe(()=>g1.groups())[0],sa=g2&&safe(()=>g2.scrollAreas())[0],u=sa&&safe(()=>sa.uiElements())[0];if(!u)throw new Error('webview root missing');return u;}
  function coll(){const r=root(),out=[];for(const xs of [safe(()=>r.buttons()),safe(()=>r.staticTexts()),safe(()=>r.headings()),safe(()=>r.checkboxes()),safe(()=>r.popUpButtons())])for(const e of xs)out.push({e,role:str(()=>e.role()),name:str(()=>e.name()),desc:str(()=>e.description())});return out;}
  function box(e){try{const q=e.position(),z=e.size();return{x:Number(q[0]),y:Number(q[1]),w:Number(z[0]),h:Number(z[1])}}catch(_){return{x:0,y:0,w:0,h:0}}}
  function exact(t,role){return coll().find(o=>(o.name===t||o.desc===t)&&(!role||o.role===role));}
  function contains(t,role){return coll().find(o=>((o.name||'').includes(t)||(o.desc||'').includes(t))&&(!role||o.role===role));}
  function bfsFind(t,role,partial){let q=[w],i=0,seen=0;while(i<q.length&&seen<500){const e=q[i++];seen++;const r=str(()=>e.role()),n=str(()=>e.name()),d=str(()=>e.description());const hit=partial?(n.includes(t)||d.includes(t)):(n===t||d===t);if(hit&&(!role||r===role))return {e,role:r,name:n,desc:d};if(['AXImage','AXSlider','AXTextField'].includes(r))continue;let kids=safe(()=>e.uiElements());for(let j=0;j<kids.length;j++)q.push(kids[j]);}return null;}
  function visibleLabel(t){for(let n=0;n<14;n++){const x=exact(t)||contains(t)||bfsFind(t,null,true);if(!x)throw new Error('label missing '+t);const b=box(x.e),wb=box(w);if(b.y>wb.y+65&&b.y<wb.y+wb.h-85)return x;se.keyCode(b.y>=wb.y+wb.h-85?121:116);delay(.12)}throw new Error('label not visible '+t)}
  function near(label,names){const l=visibleLabel(label),lb=box(l.e),ly=lb.y+lb.h/2,lx=lb.x+lb.w/2;let best=null;for(const o of coll()){if(o.role!=='AXButton'||!names.includes(o.name))continue;const b=box(o.e),score=Math.abs((b.y+b.h/2)-ly)*10+Math.abs((b.x+b.w/2)-lx);if(!best||score<best.score)best={o,score};}if(!best){for(const name of names){const o=bfsFind(name,'AXButton',false);if(o){best={o,score:0};break;}}}if(!best)throw new Error('near button missing '+label);return best.o;}
  if(cmd==='geom'){const b=box(w);return `${b.x},${b.y},${b.w},${b.h}`;}
  if(cmd==='press'){const x=exact(a1,'AXButton')||contains(a1,'AXButton')||bfsFind(a1,'AXButton',false)||bfsFind(a1,'AXButton',true);if(!x)throw new Error('button missing '+a1);x.e.click();delay(.22);return 'OK';}
  if(cmd==='contains'){const x=contains(a1,'AXButton')||bfsFind(a1,'AXButton',true);if(!x)throw new Error('button contains missing '+a1);x.e.click();delay(.22);return 'OK';}
  if(cmd==='has'){return String((exact(a1)||contains(a1)||bfsFind(a1,null,true))?1:0);}
  if(cmd==='scroll'){visibleLabel(a1);return 'OK';}
  if(cmd==='nearpress'){const x=near(a1,[a2]);x.e.click();delay(.25);return 'OK';}
  if(cmd==='feature'){const want=a2==='ON';let x=near(a1,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']),on=x.name==='ВЫКЛЮЧИТЬ';if(on!==want){x.e.click();delay(.3);x=near(a1,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']);}if((x.name==='ВЫКЛЮЧИТЬ')!==want)throw new Error('feature failed '+a1);return 'OK';}
  if(cmd==='dump'){return coll().map(o=>`${o.role}|${o.name}|${o.desc}`).join('\n');}
  throw new Error('bad cmd');
}
JXA
direct(){ python3 - "$REPORT/ui-direct-v9.js" "$PID" "$@" <<'PY2'
import subprocess,sys
try:r=subprocess.run(['/usr/bin/osascript','-l','JavaScript',sys.argv[1],sys.argv[2],*sys.argv[3:]],text=True,capture_output=True,timeout=20)
except subprocess.TimeoutExpired: print('DIRECT_UI_TIMEOUT',file=sys.stderr);raise SystemExit(124)
if r.stdout:print(r.stdout,end='')
if r.returncode:
    if r.stderr:print(r.stderr,file=sys.stderr,end='')
    raise SystemExit(r.returncode)
PY2
}
direct dump > "$REPORT/direct-ui-inventory.txt" || true
direct contains 'Нажмите для выбора папки результата'
choose_safe "$FIX/output"
sleep 1
# Override V5 recursive System Events helper for all remaining interactions.
ui(){ direct "$@"; }
'''
if old not in s: raise SystemExit('V8 output block not found')
s=s.replace(old,new,1)
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$OUT"
exec bash "$OUT"
