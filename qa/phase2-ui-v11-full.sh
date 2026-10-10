#!/bin/bash
set -Eeuo pipefail
V8="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"
V9="$GITHUB_WORKSPACE/qa/phase2-ui-v9.sh"
V8FIX="$RUNNER_TEMP/phase2-ui-v8-picker-fixed.sh"
V9RUN="$RUNNER_TEMP/phase2-ui-v11-runtime.sh"
python3 - "$V8" "$V9" "$V8FIX" "$V9RUN" <<'PY'
from pathlib import Path
import sys
v8=Path(sys.argv[1]).read_text()
v9=Path(sys.argv[2]).read_text()
old=r'''choose_safe(){ local target="$1"; /usr/bin/osascript - "$PID" "$target" <<'OSA'
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
new=r'''choose_safe(){ local target="$1"; /usr/bin/osascript - "$PID" "$target" <<'OSA'
on run argv
  set targetPid to (item 1 of argv) as integer
  set targetPath to item 2 of argv
  tell application "System Events"
    set ps to every application process whose unix id is targetPid
    if (count of ps) is not 1 then error "candidate missing"
    set proc to item 1 of ps
    tell proc to set frontmost to true
    keystroke "g" using {command down, shift down}
    delay 0.45
    set targetField to missing value
    tell proc
      try
        set targetField to text field 1 of sheet 1 of window 1
      end try
      if targetField is missing value then
        try
          set targetField to text field 1 of window 1
        end try
      end if
      if targetField is missing value then
        try
          set targetField to text field 1 of group 1 of sheet 1 of window 1
        end try
      end if
      if targetField is missing value then error "go-to-folder text field not exposed"
      set value of targetField to targetPath
    end tell
    delay 0.2
    key code 36
    delay 0.8
    key code 36
  end tell
end run
OSA
}
'''
if old not in v8: raise SystemExit('V11 choose_safe block not found')
v8=v8.replace(old,new,1)
Path(sys.argv[3]).write_text(v8)
needle='BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"'
replacement='BASE="$RUNNER_TEMP/phase2-ui-v8-picker-fixed.sh"'
if needle not in v9: raise SystemExit('V11 V9 base line missing')
v9=v9.replace(needle,replacement,1)
Path(sys.argv[4]).write_text(v9)
PY
chmod +x "$V8FIX" "$V9RUN"
exec bash "$V9RUN"
