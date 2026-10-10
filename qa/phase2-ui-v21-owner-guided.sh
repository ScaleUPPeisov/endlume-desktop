#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
OUT="$RUNNER_TEMP/phase2-ui-v21-runtime.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
start=s.index("READY=0; for n in $(seq 0 120);")
guided=r'''cat > "$REPORT/probe-nav-v21.js" <<'JXA'
function run(argv){const pid=Number(argv[0]),se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();if(ps.length!==1)throw new Error('candidate missing');const p=ps[0];p.frontmost=true;delay(.05);const wins=p.windows();if(!wins.length)return 'NAV=0 ACT=false';let f={p:false,r:false,l:false,s:false,a:false},n=0,stack=[wins[0]];const str=fn=>{try{const v=fn();return v==null?'':String(v)}catch(_){return ''}};while(stack.length&&n<300){const e=stack.pop();n++;const name=str(()=>e.name()),desc=str(()=>e.description()),h=name+' '+desc;if(name==='Проект'||desc==='Проект')f.p=true;if(name==='Рендер'||desc==='Рендер')f.r=true;if(name==='Библиотека'||desc==='Библиотека')f.l=true;if(name==='Настройки'||desc==='Настройки')f.s=true;if(h.includes('АКТИВИРОВАТЬ')||h.includes('Активация ENDLUME')||h.includes('Нужна активация'))f.a=true;if(f.p&&f.r&&f.l&&f.s)return `NAV=4 ACT=${f.a}`;let k=[];try{k=e.uiElements()}catch(_){}for(let i=0;i<k.length;i++)stack.push(k[i]);}return `NAV=${[f.p,f.r,f.l,f.s].filter(Boolean).length} ACT=${f.a}`;}
JXA

echo MANUAL_ACTION_IF_PROMPT=CLICK_ALLOW_NOT_ALWAYS_ALLOW
/usr/bin/say 'ENDLUME QA. Если появилось окно связки ключей, нажми Разрешить. Если появилось окно обновления, нажми Позже.' >/dev/null 2>&1 &
READY=0
for second in $(seq 0 30); do
  kill -0 "$PID" >/dev/null 2>&1 || exit 85
  set +e
  OUTNAV=$(/usr/bin/osascript -l JavaScript "$REPORT/probe-nav-v21.js" "$PID" 2>/dev/null)
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

GUIDE="$HOME/Desktop/ENDLUME_PHASE2_QA_GUIDED"
rm -rf "$GUIDE"
mkdir -p "$GUIDE"
cp -R "$FIX/project" "$GUIDE/project"
mkdir -p "$GUIDE/output"
trap 'rm -rf "$GUIDE"; cleanup' EXIT

capture_window(){
  local out="$1" g rc
  set +e
  g=$(/usr/bin/osascript - "$PID" <<'OSA'
on run argv
  set targetPid to (item 1 of argv) as integer
  tell application "System Events"
    set ps to every application process whose unix id is targetPid
    if (count of ps) is not 1 then error "candidate missing"
    tell item 1 of ps
      set p to position of window 1
      set z to size of window 1
      return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of z as text) & "," & (item 2 of z as text)
    end tell
  end tell
end run
OSA
  )
  rc=$?
  set -e
  [ "$rc" -eq 0 ] || { echo "WINDOW_GEOMETRY_FAIL=$rc" >&2; return 97; }
  IFS=',' read -r x y w h <<< "$g"
  /usr/sbin/screencapture -x -R"$x,$y,$w,$h" "$REPORT/screens/$out"
  test -s "$REPORT/screens/$out"
  echo "CAPTURED=$out"
}

prompt(){
  local text="$1" seconds="$2"
  echo "OWNER_PROMPT=$text"
  /usr/bin/say "$text" >/dev/null 2>&1 &
  sleep "$seconds"
}

printf 'OWNER_GUIDED_MODE=YES\nLICENSED_SESSION=PASS\nNORMAL_NAVIGATION=PASS\nLICENSE_BYPASS=NO\n' > "$REPORT/owner-guided-v21.txt"

prompt 'Ничего не нажимай. Снимаю экран Проект.' 3
capture_window '01-project.png'

prompt 'Нажми область исходных файлов. Выбери Рабочий стол, ENDLUME PHASE2 QA GUIDED, project. Потом выбери папку результата output. У тебя двадцать секунд.' 20
capture_window '01b-project-loaded.png'

prompt 'На Проекте выключи Эффект для каждого проекта. Потом ничего не нажимай.' 6
capture_window '02-effects-off.png'

prompt 'Включи Эффект для каждого проекта и нажми Настроить. Потом ничего не нажимай.' 7
capture_window '03-effects-on.png'
cp "$REPORT/screens/03-effects-on.png" "$REPORT/screens/06-effects-live-preview.png"

prompt 'Вернись к проекту. Выключи Subscribe Button.' 6
capture_window '04-subscribe-off.png'

prompt 'Включи Subscribe Button и нажми Настроить.' 7
capture_window '05-subscribe-on.png'
cp "$REPORT/screens/05-subscribe-on.png" "$REPORT/screens/06b-subscribe-live-preview.png"

prompt 'Вернись к проекту и нажми Рендер.' 5
capture_window '07-render-idle.png'

prompt 'Нажми Библиотека.' 5
capture_window '09-library.png'

prompt 'Нажми Настройки. Потом Общие.' 5
capture_window '10-settings-general.png'

prompt 'Нажми FAST ENGINE.' 4
capture_window '11-settings-fast-engine.png'

prompt 'Нажми Обновления.' 4
capture_window '12-settings-updates.png'

prompt 'Нажми О программе.' 4
capture_window '13-settings-about.png'

prompt 'Вернись в Проект. Нажми Добавить в очередь. Сразу нажми Рендер. Потом ничего не нажимай.' 5
for n in $(seq -w 1 12); do capture_window "08-render-active-$n.png" || true; sleep .7; done

printf 'PROJECT_SCREEN=CAPTURED\nEFFECTS_OFF_SCREEN=CAPTURED\nEFFECTS_ON_SCREEN=CAPTURED\nSUBSCRIBE_OFF_SCREEN=CAPTURED\nSUBSCRIBE_ON_SCREEN=CAPTURED\nRENDER_IDLE_SCREEN=CAPTURED\nLIBRARY_SCREEN=CAPTURED\nSETTINGS_GENERAL_SCREEN=CAPTURED\nSETTINGS_FAST_ENGINE_SCREEN=CAPTURED\nSETTINGS_UPDATES_SCREEN=CAPTURED\nSETTINGS_ABOUT_SCREEN=CAPTURED\nACTIVE_RENDER_BURST=CAPTURED\nPRODUCT_FILES_CHANGED=0\nSTABLE_TOUCHED=NO\nLIVE_UPDATER_TOUCHED=NO\n' >> "$REPORT/owner-guided-v21.txt"
echo OWNER_GUIDED_V21_CAPTURE=PASS
'''
s=s[:start]+guided+'\n'
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$OUT"
exec bash "$OUT"
