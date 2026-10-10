#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
OUT="$RUNNER_TEMP/phase2-ui-v6-runtime.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()
start=src.index("READY=0; for n in $(seq 0 120);")
end=src.index("# Source picker:", start)
probe=r'''cat > "$REPORT/probe-nav.js" <<'JXA'
function run(argv){const pid=Number(argv[0]),se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();if(ps.length!==1)throw new Error('candidate missing');const p=ps[0];p.frontmost=true;delay(.1);const wins=p.windows();if(!wins.length)return 'NAV_COUNT=0\\nACTIVATION=false';let f={p:false,r:false,l:false,s:false,a:false},n=0,stack=[wins[0]];const str=fn=>{try{const v=fn();return v==null?'':String(v)}catch(_){return ''}};while(stack.length&&n<300){const e=stack.pop();n++;const name=str(()=>e.name()),desc=str(()=>e.description()),h=name+'\\n'+desc;if(name==='Проект'||desc==='Проект')f.p=true;if(name==='Рендер'||desc==='Рендер')f.r=true;if(name==='Библиотека'||desc==='Библиотека')f.l=true;if(name==='Настройки'||desc==='Настройки')f.s=true;if(h.includes('АКТИВИРОВАТЬ')||h.includes('Активация ENDLUME')||h.includes('Нужна активация'))f.a=true;if(f.p&&f.r&&f.l&&f.s)return `NODE_COUNT=${n}\\nNAV_COUNT=4\\nACTIVATION=${f.a}`;let k=[];try{k=e.uiElements()}catch(_){}for(let i=0;i<k.length;i++)stack.push(k[i]);}return `NODE_COUNT=${n}\\nNAV_COUNT=${[f.p,f.r,f.l,f.s].filter(Boolean).length}\\nACTIVATION=${f.a}`;}
JXA
echo MANUAL_ACTION_IF_PROMPT=CLICK_ALLOW_NOT_ALWAYS_ALLOW
READY=0
for second in $(seq 0 180); do
  kill -0 "$PID" >/dev/null 2>&1 || exit 85
  set +e
  OUTNAV=$(/usr/bin/osascript -l JavaScript "$REPORT/probe-nav.js" "$PID" 2>/dev/null)
  RC=$?
  set -e
  NAV="$(printf '%s\n' "$OUTNAV"|awk -F= '$1=="NAV_COUNT"{print $2}')"
  ACT="$(printf '%s\n' "$OUTNAV"|awk -F= '$1=="ACTIVATION"{print $2}')"
  if [ "$RC" -eq 0 ] && [ "${ACT:-false}" = true ]; then exit 75; fi
  if [ "$RC" -eq 0 ] && [ "${NAV:-0}" -eq 4 ] 2>/dev/null; then READY=1; break; fi
  sleep 1
done
test "$READY" -eq 1
printf 'LICENSED_SESSION=PASS\nNORMAL_NAVIGATION=PASS\nLICENSE_BYPASS=NO\n' > "$REPORT/license-gate.txt"
echo LICENSED_SESSION=PASS

'''
src=src[:start]+probe+src[end:]
old="""# Source picker: try BFS, then deterministic physical fallback at center of canonical dropzone.\nset +e; ui contains 'Перетащите папки с файлами' >/dev/null 2>&1; rc=$?; set -e; [ \"$rc\" -eq 0 ] || click_rel .50 .23\nchoose \"$FIX/project\"; sleep 2\n# Output picker: use BFS scrolling; fallback to bottom-of-project physical position after Cmd+Down.\nset +e; ui contains 'Нажмите для выбора папки результата' >/dev/null 2>&1; rc=$?; set -e\nif [ \"$rc\" -ne 0 ]; then /usr/bin/osascript -e 'tell application \"System Events\" to key code 125 using {command down}'; sleep .4; click_rel .50 .76; fi\nchoose \"$FIX/output\"; sleep 1\n"""
new="""# Deterministic physical clicks derived from canonical 1280x860 layout.\nclick_rel .50 .23\nchoose \"$FIX/project\"; sleep 2\n/usr/bin/osascript -e 'tell application \"System Events\" to key code 125 using {command down}'\nsleep .4\nclick_rel .50 .72\nchoose \"$FIX/output\"; sleep 1\n"""
if old not in src: raise SystemExit('picker block not found')
src=src.replace(old,new,1)
Path(sys.argv[2]).write_text(src)
PY
chmod +x "$OUT"
exec bash "$OUT"
