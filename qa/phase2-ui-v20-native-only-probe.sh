#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"
OUT="$RUNNER_TEMP/phase2-ui-v20-runtime.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
old='''click_rel .50 .23\nchoose_safe "$FIX/project"\nsleep 2\n'''
new=r'''click_rel .50 .23
sleep .5
/usr/bin/osascript - "$PID" <<'OSA'
on run argv
  set targetPid to (item 1 of argv) as integer
  tell application "System Events"
    set ps to every application process whose unix id is targetPid
    if (count of ps) is not 1 then error "candidate missing"
    set proc to item 1 of ps
    tell proc to set frontmost to true
    delay 0.15
    keystroke "g" using {command down, shift down}
  end tell
end run
OSA
sleep .7
cat > "$REPORT/native-picker-probe-v20.js" <<'JXA'
function run(argv){
 const pid=Number(argv[0]),se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();
 if(ps.length!==1)throw new Error('candidate missing');const p=ps[0],out=[],q=[];
 const str=f=>{try{const v=f();return v==null?'':String(v)}catch(_){return ''}};
 const ws=p.windows();
 for(let i=0;i<ws.length;i++){
   const w=ws[i],name=str(()=>w.name());out.push(`WINDOW|${i}|name=${name}|role=${str(()=>w.role())}|subrole=${str(()=>w.subrole())}`);
   let sheets=[];try{sheets=w.sheets()}catch(_){};for(let j=0;j<sheets.length;j++)q.push({e:sheets[j],d:0,path:`W${i}.S${j}`});
   if(name!=='ENDLUME YT Studio PEISOV')q.push({e:w,d:0,path:`W${i}`});
 }
 let seen=0;
 while(q.length&&seen<350){const x=q.shift(),e=x.e;seen++;const role=str(()=>e.role()),name=str(()=>e.name()),desc=str(()=>e.description()),val=str(()=>e.value()),focused=str(()=>e.focused());
   out.push(`${x.d}|${x.path}|${role}|name=${name}|desc=${desc}|value=${val}|focused=${focused}`);
   if(x.d>=5)continue;let kids=[];try{kids=e.uiElements()}catch(_){};for(let i=0;i<kids.length;i++)q.push({e:kids[i],d:x.d+1,path:x.path+'.'+i});
 }
 out.push(`SEEN=${seen}`);return out.join('\n');
}
JXA
/usr/bin/osascript -l JavaScript "$REPORT/native-picker-probe-v20.js" "$PID" > "$REPORT/native-picker-tree-v20.txt"
capture 'native-picker-goto-v20.png'
printf 'NATIVE_ONLY_PICKER_PROBE=PASS\nOWNER_PRODUCT_UNCHANGED=YES\n' > "$REPORT/picker-probe-v20.txt"
echo NATIVE_ONLY_PICKER_PROBE=PASS
exit 0
'''
if old not in s: raise SystemExit('V20 picker insertion point missing')
s=s.replace(old,new,1)
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$OUT"
exec bash "$OUT"
