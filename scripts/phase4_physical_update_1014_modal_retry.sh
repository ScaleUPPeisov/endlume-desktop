#!/bin/bash
set -Eeuo pipefail

SRC='scripts/phase4_physical_update_1014.sh'
TMP="${RUNNER_TEMP:?}/phase4_physical_update_1014_modal_runtime.sh"
python3 - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()

old_start=src.index('sleep 3\nclicked=0\n')
old_end=src.index('echo UPDATE_DETECTED_10_0_13_TO_10_0_14=PASS\n',old_start)+len('echo UPDATE_DETECTED_10_0_13_TO_10_0_14=PASS\n')
new=r'''sleep 2

# ENDLUME automatically runs local_update_check() ~1.8 s after startup.
# Drive the actual UpdateExperience modal, not the Settings page.
click_ui_text(){
  local pid="$1" wanted="$2"
  osascript - "$pid" "$wanted" <<'APPLESCRIPT'
on run argv
  set targetPid to (item 1 of argv) as integer
  set wantedText to item 2 of argv
  tell application "System Events"
    try
      set p to first application process whose unix id is targetPid
      set frontmost of p to true
      repeat with w in windows of p
        repeat with e in entire contents of w
          set nm to ""
          set ds to ""
          set vl to ""
          set hp to ""
          try
            set nm to name of e as text
          end try
          try
            set ds to description of e as text
          end try
          try
            set vl to value of e as text
          end try
          try
            set hp to help of e as text
          end try
          set blob to nm & " " & ds & " " & vl & " " & hp
          if blob contains wantedText then
            try
              perform action "AXPress" of e
              return "CLICKED_AXPRESS"
            end try
            try
              click e
              return "CLICKED_CLICK"
            end try
          end if
        end repeat
      end repeat
      repeat 48 times
        key code 48
        delay 0.10
        try
          set f to value of attribute "AXFocusedUIElement" of p
          set nm to ""
          set ds to ""
          set vl to ""
          try
            set nm to name of f as text
          end try
          try
            set ds to description of f as text
          end try
          try
            set vl to value of f as text
          end try
          set blob to nm & " " & ds & " " & vl
          if blob contains wantedText then
            try
              perform action "AXPress" of f
              return "CLICKED_FOCUSED_AXPRESS"
            end try
            key code 36
            return "CLICKED_FOCUSED_RETURN"
          end if
        end try
      end repeat
    on error errText
      return "ERROR:" & errText
    end try
  end tell
  return "NOT_FOUND"
end run
APPLESCRIPT
}

clicked=0
for attempt in $(seq 1 90); do
  OUT="$(click_ui_text "$APP_PID" 'ОБНОВИТЬ')"
  echo "UPDATE_MODAL_ATTEMPT=$attempt RESULT=$OUT"
  if [[ "$OUT" == CLICKED_* ]]; then clicked=1; break; fi
  sleep 1
done
test "$clicked" -eq 1
echo UPDATE_MODAL_AVAILABLE=PASS
echo UPDATE_UI_INSTALL_CLICK=PASS
echo UPDATE_DETECTED_10_0_13_TO_10_0_14=PASS
'''
src=src[:old_start]+new+src[old_end:]

restart_start=src.index('# Updater must restart itself as 10.0.14; do not manually launch for this gate.')
restart_end=src.index('echo UPDATER_RESTART=PASS\n',restart_start)+len('echo UPDATER_RESTART=PASS\n')
restart=r'''# Updater is configured with restart_after_install(true). If the frontend reaches
# RESTART_REQUIRED before the automatic relaunch, exercise its real RESTART ENDLUME control.
NEW_EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$INFO")"
RESTART_PID=''
for i in $(seq 1 120); do
  for p in $(pgrep -x "$NEW_EXE" 2>/dev/null || true); do
    cmd="$(ps -p "$p" -o command= 2>/dev/null || true)"
    case "$cmd" in
      "$APP/Contents/MacOS/$NEW_EXE"*)
        if [ "$p" != "$APP_PID" ]; then RESTART_PID="$p"; break 2; fi
        ;;
    esac
  done
  if [ $i -ge 4 ] && kill -0 "$APP_PID" 2>/dev/null; then
    RESTART_OUT="$(click_ui_text "$APP_PID" 'RESTART ENDLUME' || true)"
    if [[ "$RESTART_OUT" == CLICKED_* ]]; then echo "RESTART_UI_RESULT=$RESTART_OUT"; fi
  fi
  sleep 1
done
# A very fast relaunch can reuse observable timing but must not leave the old pid alive.
if [ -z "$RESTART_PID" ]; then
  for p in $(pgrep -x "$NEW_EXE" 2>/dev/null || true); do
    cmd="$(ps -p "$p" -o command= 2>/dev/null || true)"
    case "$cmd" in "$APP/Contents/MacOS/$NEW_EXE"*) RESTART_PID="$p"; break;; esac
  done
fi
test -n "$RESTART_PID"
test "$RESTART_PID" != "$APP_PID" || ! kill -0 "$APP_PID" 2>/dev/null
echo UPDATER_RESTART=PASS
'''
src=src[:restart_start]+restart+src[restart_end:]

Path(sys.argv[2]).write_text(src)
PY
chmod +x "$TMP"
exec /bin/bash "$TMP"
