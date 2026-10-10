#!/bin/bash
set -Eeuo pipefail
V5="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
V8="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"
V9="$GITHUB_WORKSPACE/qa/phase2-ui-v9.sh"
P5="$RUNNER_TEMP/phase2-ui-v17-v5.sh"
P8="$RUNNER_TEMP/phase2-ui-v17-v8.sh"
P9="$RUNNER_TEMP/phase2-ui-v17-v9.sh"
python3 - "$V5" "$V8" "$V9" "$P5" "$P8" "$P9" <<'PY'
from pathlib import Path
import sys
v5=Path(sys.argv[1]).read_text(); v8=Path(sys.argv[2]).read_text(); v9=Path(sys.argv[3]).read_text()
old='$RUNNER_TEMP/endlume-phase2-v5-fixture'; new='$HOME/Desktop/ENDLUME_PHASE2_QA_${GITHUB_RUN_ID}'
if old not in v5: raise SystemExit('V17 FIX path missing')
v5=v5.replace(old,new,1)
repls={
"ui press 'Проект'; capture '01-project.png'":"capture '01-project.png'",
"ui press 'Рендер'; sleep .5; capture '07-render-idle.png'":"click_rel .81 .065; sleep .8; capture '07-render-idle.png'",
"ui press 'Библиотека'; sleep .5; capture '09-library.png'":"click_rel .87 .065; sleep .8; capture '09-library.png'",
"ui press 'Настройки'; sleep .5; ui press 'ОБЩИЕ'":"click_rel .955 .065; sleep .8; ui press 'ОБЩИЕ'",
"ui press 'Проект'; ui feature 'Эффект для каждого проекта' OFF":"click_rel .755 .065; sleep .8; ui feature 'Эффект для каждого проекта' OFF",
}
for a,b in repls.items():
    if a not in v5: raise SystemExit('V17 nav pattern missing: '+a)
    v5=v5.replace(a,b,1)
Path(sys.argv[4]).write_text(v5)
old8='BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"'; new8='BASE="$RUNNER_TEMP/phase2-ui-v17-v5.sh"'
if old8 not in v8: raise SystemExit('V17 V8 base missing')
v8=v8.replace(old8,new8,1)
old_picker=r'''choose_safe(){ local target="$1"; /usr/bin/osascript - "$PID" "$target" <<'OSA'
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
'''
new_picker=r'''choose_safe(){ local target="$1"; /usr/bin/osascript - "$PID" "$target" <<'OSA'
on run argv
  set targetPid to (item 1 of argv) as integer
  set targetPath to item 2 of argv
  set oldClipboard to the clipboard
  try
    set the clipboard to targetPath
    tell application "System Events"
      set ps to every application process whose unix id is targetPid
      if (count of ps) is not 1 then error "candidate missing"
      set proc to item 1 of ps
      tell proc to set frontmost to true
      keystroke "g" using {command down, shift down}
      delay 0.45
      keystroke "a" using {command down}
      delay 0.08
      keystroke "v" using {command down}
      delay 0.25
      key code 36
      delay 0.85
      key code 36
      delay 1.0
    end tell
  on error errMsg number errNum
    set the clipboard to oldClipboard
    error errMsg number errNum
  end try
  set the clipboard to oldClipboard
end run
OSA
}
'''
if old_picker not in v8: raise SystemExit('V17 picker block missing')
v8=v8.replace(old_picker,new_picker,1)
Path(sys.argv[5]).write_text(v8)
old9='BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"'; new9='BASE="$RUNNER_TEMP/phase2-ui-v17-v8.sh"'
if old9 not in v9: raise SystemExit('V17 V9 base missing')
v9=v9.replace(old9,new9,1)
Path(sys.argv[6]).write_text(v9)
PY
chmod +x "$P5" "$P8" "$P9"
echo "PICKER_MODE=CLIPBOARD_DOUBLE_ENTER"
exec bash "$P9"
