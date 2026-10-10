#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
OUT="$RUNNER_TEMP/phase2-ui-v8-runtime.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()
start=src.index("READY=0; for n in $(seq 0 120);")
end=src.index("# Source picker:", start)
block=r'''cat > "$REPORT/probe-nav-v8.js" <<'JXA'
function run(argv){const pid=Number(argv[0]),se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();if(ps.length!==1)throw new Error('candidate missing');const p=ps[0];p.frontmost=true;delay(.08);const wins=p.windows();if(!wins.length)return 'NAV=0 ACT=false';let f={p:false,r:false,l:false,s:false,a:false},n=0,stack=[wins[0]];const str=fn=>{try{const v=fn();return v==null?'':String(v)}catch(_){return ''}};while(stack.length&&n<300){const e=stack.pop();n++;const name=str(()=>e.name()),desc=str(()=>e.description()),h=name+' '+desc;if(name==='Проект'||desc==='Проект')f.p=true;if(name==='Рендер'||desc==='Рендер')f.r=true;if(name==='Библиотека'||desc==='Библиотека')f.l=true;if(name==='Настройки'||desc==='Настройки')f.s=true;if(h.includes('АКТИВИРОВАТЬ')||h.includes('Активация ENDLUME')||h.includes('Нужна активация'))f.a=true;if(f.p&&f.r&&f.l&&f.s)return `NAV=4 ACT=${f.a}`;let k=[];try{k=e.uiElements()}catch(_){}for(let i=0;i<k.length;i++)stack.push(k[i]);}return `NAV=${[f.p,f.r,f.l,f.s].filter(Boolean).length} ACT=${f.a}`;}
JXA
echo MANUAL_ACTION_IF_PROMPT=CLICK_ALLOW_NOT_ALWAYS_ALLOW
READY=0
for second in $(seq 0 180); do
  kill -0 "$PID" >/dev/null 2>&1 || exit 85
  set +e
  OUTNAV=$(/usr/bin/osascript -l JavaScript "$REPORT/probe-nav-v8.js" "$PID" 2>/dev/null)
  RC=$?
  set -e
  NAV="$(printf '%s' "$OUTNAV"|sed -n 's/.*NAV=\([0-9][0-9]*\).*/\1/p')"
  ACT="$(printf '%s' "$OUTNAV"|sed -n 's/.*ACT=\([^ ]*\).*/\1/p')"
  if [ "$RC" -eq 0 ] && [ "${ACT:-false}" = true ]; then exit 75; fi
  if [ "$RC" -eq 0 ] && [ "${NAV:-0}" -eq 4 ] 2>/dev/null; then READY=1; break; fi
  sleep 1
done
test "$READY" -eq 1
printf 'LICENSED_SESSION=PASS\nNORMAL_NAVIGATION=PASS\nLICENSE_BYPASS=NO\n' > "$REPORT/license-gate.txt"
echo LICENSED_SESSION=PASS

cat > "$REPORT/dismiss-update-v8.js" <<'JXA'
function run(argv){const pid=Number(argv[0]),se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();if(ps.length!==1)throw new Error('candidate missing');const p=ps[0];p.frontmost=true;delay(.05);const wins=p.windows();if(!wins.length)return 'NO_WINDOW';let n=0,stack=[wins[0]];const str=fn=>{try{const v=fn();return v==null?'':String(v)}catch(_){return ''}};while(stack.length&&n<350){const e=stack.pop();n++;const role=str(()=>e.role()),name=str(()=>e.name()),desc=str(()=>e.description());if(role==='AXButton'&&(name==='ПОЗЖЕ'||desc==='ПОЗЖЕ')){e.click();delay(.35);return 'UPDATE_DISMISSED'}let k=[];try{k=e.uiElements()}catch(_){}for(let i=0;i<k.length;i++)stack.push(k[i]);}return 'NO_UPDATE_DIALOG';}
JXA
set +e
DISMISS=$(/usr/bin/osascript -l JavaScript "$REPORT/dismiss-update-v8.js" "$PID" 2>/dev/null)
DRC=$?
set -e
printf 'UPDATE_OVERLAY=%s RC=%s\n' "${DISMISS:-UNKNOWN}" "$DRC" > "$REPORT/update-overlay.txt"
sleep .5

choose_safe(){ local target="$1"; /usr/bin/osascript - "$PID" "$target" <<'OSA'
on run argv
  set targetPid to (item 1 of argv) as integer
  set targetPath to item 2 of argv
  tell application "System Events"
    set ps to every application process whose unix id is targetPid
    if (count of ps) is not 1 then error "candidate missing"
    tell item 1 of ps to set frontmost to true
    keystroke "g" using {command down, shift down}
    delay 0.4
    keystroke targetPath
    delay 0.2
    key code 36
    delay 0.7
    key code 36
  end tell
end run
OSA
}

# Canonical 1280x860 project layout: source dropzone center.
click_rel .50 .23
choose_safe "$FIX/project"
sleep 2
# Scroll to project bottom; output picker sits above fixed queue footer.
/usr/bin/osascript -e 'tell application "System Events" to key code 125 using {command down}'
sleep .4
click_rel .50 .72
choose_safe "$FIX/output"
sleep 1

'''
src=src[:start]+block+src[end:]
# Remove the old source/output picker sequence; V8 already performed both above.
old="""# Source picker: try BFS, then deterministic physical fallback at center of canonical dropzone.\nset +e; ui contains 'Перетащите папки с файлами' >/dev/null 2>&1; rc=$?; set -e; [ \"$rc\" -eq 0 ] || click_rel .50 .23\nchoose \"$FIX/project\"; sleep 2\n# Output picker: use BFS scrolling; fallback to bottom-of-project physical position after Cmd+Down.\nset +e; ui contains 'Нажмите для выбора папки результата' >/dev/null 2>&1; rc=$?; set -e\nif [ \"$rc\" -ne 0 ]; then /usr/bin/osascript -e 'tell application \"System Events\" to key code 125 using {command down}'; sleep .4; click_rel .50 .76; fi\nchoose \"$FIX/output\"; sleep 1\n"""
if old not in src: raise SystemExit('old picker sequence missing')
src=src.replace(old,'',1)
Path(sys.argv[2]).write_text(src)
PY
chmod +x "$OUT"
exec bash "$OUT"
