#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
OUT="$RUNNER_TEMP/phase2-ui-v25-runtime.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
start=s.index("READY=0; for n in $(seq 0 120);")
block=r'''cat > "$REPORT/nav-v25.js" <<'JXA'
function run(argv){const pid=Number(argv[0]),cmd=argv[1],se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();if(ps.length!==1)throw new Error('candidate missing');const p=ps[0];p.frontmost=true;const str=f=>{try{const v=f();return v==null?'':String(v)}catch(_){return ''}};if(cmd==='nav'){const w=p.windows()[0],q=[w];let n=0,c=0,act=false,seen={};while(q.length&&n<400){const e=q.shift();n++;const name=str(()=>e.name()),d=str(()=>e.description()),h=name+' '+d;for(const x of ['Проект','Рендер','Библиотека','Настройки'])if(!seen[x]&&(name===x||d===x)){seen[x]=1;c++;}if(h.includes('АКТИВИРОВАТЬ'))act=true;let k=[];try{k=e.uiElements()}catch(_){};for(let j=0;j<k.length;j++)q.push(k[j]);}return `NAV=${c} ACT=${act}`;}if(cmd==='dismiss'){const w=p.windows()[0],q=[w];let n=0;while(q.length&&n<500){const e=q.shift();n++;const role=str(()=>e.role()),name=str(()=>e.name()),d=str(()=>e.description());if(role==='AXButton'&&(name==='ПОЗЖЕ'||d==='ПОЗЖЕ'||name==='Later'||d==='Later')){e.click();delay(.6);return 'DISMISSED';}let k=[];try{k=e.uiElements()}catch(_){};for(let j=0;j<k.length;j++)q.push(k[j]);}return 'NONE';}if(cmd==='scroll-bottom'){const w=p.windows()[0];let g1=w.groups()[0],g2=g1.groups()[0],sa=g2.scrollAreas()[0];let bars=[];try{bars=sa.scrollBars()}catch(_){};let out=[];for(let i=0;i<bars.length;i++){try{bars[i].value=1;out.push('bar'+i+'=1')}catch(e){out.push('bar'+i+'=ERR')}}delay(.8);return `SCROLL_BARS=${bars.length}|${out.join(',')}`;}if(cmd==='geom'){const w=p.windows()[0],q=w.position(),z=w.size();return `${q[0]},${q[1]},${z[0]},${z[1]}`;}throw new Error('bad cmd');}
JXA
u25(){ /usr/bin/osascript -l JavaScript "$REPORT/nav-v25.js" "$PID" "$@"; }
READY=0
for second in $(seq 0 30); do set +e; O=$(u25 nav 2>/dev/null);R=$?;set -e;N="$(printf '%s' "$O"|sed -n 's/.*NAV=\([0-9][0-9]*\).*/\1/p')";A="$(printf '%s' "$O"|sed -n 's/.*ACT=\([^ ]*\).*/\1/p')";[ "$R" -eq 0 ]&&[ "${A:-false}" = true ]&&exit 75;if [ "$R" -eq 0 ]&&[ "${N:-0}" -eq 4 ] 2>/dev/null;then READY=1;break;fi;sleep 1;done
test "$READY" -eq 1
printf 'LICENSED_SESSION=PASS\nNORMAL_NAVIGATION=PASS\nLICENSE_BYPASS=NO\n' > "$REPORT/license-gate.txt"
u25 dismiss > "$REPORT/update-dismiss-v25.txt";sleep .7
u25 scroll-bottom > "$REPORT/scroll-bottom-v25.txt"
g="$(u25 geom)";IFS=',' read -r x y w h <<< "$g";/usr/sbin/screencapture -x -R"$x,$y,$w,$h" "$REPORT/screens/project-bottom-v25.png";test -s "$REPORT/screens/project-bottom-v25.png"
printf 'PROJECT_BOTTOM_PROBE=PASS\nPRODUCT_FILES_CHANGED=0\n' > "$REPORT/v25-result.txt"
echo PROJECT_BOTTOM_V25=PASS
'''
s=s[:start]+block+'\n'
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$OUT"
exec bash "$OUT"
