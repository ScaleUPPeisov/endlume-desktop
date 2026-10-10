#!/bin/bash
set -Eeuo pipefail
V5="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
V8="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"
V9="$GITHUB_WORKSPACE/qa/phase2-ui-v9.sh"
P5="$RUNNER_TEMP/phase2-ui-v18-v5.sh"
P8="$RUNNER_TEMP/phase2-ui-v18-v8.sh"
P9="$RUNNER_TEMP/phase2-ui-v18-v9.sh"
python3 - "$V5" "$V8" "$V9" "$P5" "$P8" "$P9" <<'PY'
from pathlib import Path
import sys
v5=Path(sys.argv[1]).read_text(); v8=Path(sys.argv[2]).read_text(); v9=Path(sys.argv[3]).read_text()
old='$RUNNER_TEMP/endlume-phase2-v5-fixture'; new='$HOME/Desktop/ENDLUME_PHASE2_QA_${GITHUB_RUN_ID}'
if old not in v5: raise SystemExit('V18 FIX path missing')
v5=v5.replace(old,new,1)
repls={
"ui press 'Проект'; capture '01-project.png'":"capture '01-project.png'",
"ui press 'Рендер'; sleep .5; capture '07-render-idle.png'":"click_rel .81 .065; sleep .8; capture '07-render-idle.png'",
"ui press 'Библиотека'; sleep .5; capture '09-library.png'":"click_rel .87 .065; sleep .8; capture '09-library.png'",
"ui press 'Настройки'; sleep .5; ui press 'ОБЩИЕ'":"click_rel .955 .065; sleep .8; ui press 'ОБЩИЕ'",
"ui press 'Проект'; ui feature 'Эффект для каждого проекта' OFF":"click_rel .755 .065; sleep .8; ui feature 'Эффект для каждого проекта' OFF",
}
for a,b in repls.items():
    if a not in v5: raise SystemExit('V18 nav pattern missing: '+a)
    v5=v5.replace(a,b,1)
Path(sys.argv[4]).write_text(v5)
old8='BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"'; new8='BASE="$RUNNER_TEMP/phase2-ui-v18-v5.sh"'
if old8 not in v8: raise SystemExit('V18 V8 base missing')
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
  tell application "System Events"
    set ps to every application process whose unix id is targetPid
    if (count of ps) is not 1 then error "candidate missing"
    set proc to item 1 of ps
    tell proc to set frontmost to true
    keystroke "g" using {command down, shift down}
    delay 0.55
    set pathSet to false
    tell proc
      repeat with w in windows
        try
          repeat with s in sheets of w
            try
              if (count of text fields of s) > 0 then
                set value of text field 1 of s to targetPath
                set pathSet to true
                exit repeat
              end if
            end try
          end repeat
        end try
        if pathSet then exit repeat
      end repeat
    end tell
    if pathSet is false then error "go-to-folder field missing"
    key code 36
    delay 0.9
    set clicked to false
    tell proc
      repeat with w in windows
        try
          if exists button "Open" of w then
            click button "Open" of w
            set clicked to true
            exit repeat
          end if
        end try
        try
          repeat with s in sheets of w
            try
              if exists button "Open" of s then
                click button "Open" of s
                set clicked to true
                exit repeat
              end if
            end try
            try
              if exists button "Choose" of s then
                click button "Choose" of s
                set clicked to true
                exit repeat
              end if
            end try
            try
              if exists button "Выбрать" of s then
                click button "Выбрать" of s
                set clicked to true
                exit repeat
              end if
            end try
          end repeat
        end try
        if clicked then exit repeat
      end repeat
    end tell
    if clicked is false then key code 36
    delay 1.2
  end tell
end run
OSA
}
'''
if old_picker not in v8: raise SystemExit('V18 picker block missing')
v8=v8.replace(old_picker,new_picker,1)
Path(sys.argv[5]).write_text(v8)
old9='BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"'; new9='BASE="$RUNNER_TEMP/phase2-ui-v18-v8.sh"'
if old9 not in v9: raise SystemExit('V18 V9 base missing')
v9=v9.replace(old9,new9,1)
Path(sys.argv[6]).write_text(v9)
PY
chmod +x "$P5" "$P8" "$P9"
echo "PICKER_MODE=NATIVE_FIELD_DIRECT"
exec bash "$P9"
