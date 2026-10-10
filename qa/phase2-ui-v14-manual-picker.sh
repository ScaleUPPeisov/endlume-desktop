#!/bin/bash
set -Eeuo pipefail
V5="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
V8="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"
V11="$GITHUB_WORKSPACE/qa/phase2-ui-v11-full.sh"
P5="$RUNNER_TEMP/phase2-ui-v14-v5.sh"
P8="$RUNNER_TEMP/phase2-ui-v14-v8.sh"
P11="$RUNNER_TEMP/phase2-ui-v14-v11.sh"
python3 - "$V5" "$V8" "$V11" "$P5" "$P8" "$P11" <<'PY'
from pathlib import Path
import sys
v5=Path(sys.argv[1]).read_text()
v8=Path(sys.argv[2]).read_text()
v11=Path(sys.argv[3]).read_text()
old='$RUNNER_TEMP/endlume-phase2-v5-fixture'
new='$HOME/Desktop/ENDLUME_PHASE2_QA_${GITHUB_RUN_ID}'
if old not in v5: raise SystemExit('V14 FIX path missing')
v5=v5.replace(old,new,1)
Path(sys.argv[4]).write_text(v5)
old8='BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"'
new8='BASE="$RUNNER_TEMP/phase2-ui-v14-v5.sh"'
if old8 not in v8: raise SystemExit('V14 V8 base missing')
v8=v8.replace(old8,new8,1)
Path(sys.argv[5]).write_text(v8)
old11='V8="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"'
new11='V8="$RUNNER_TEMP/phase2-ui-v14-v8.sh"'
if old11 not in v11: raise SystemExit('V14 V11 base missing')
v11=v11.replace(old11,new11,1)
start=v11.index("new=r'''choose_safe(){")
end=v11.index("\n'''\nif old not in v8", start)
picker=r'''choose_safe(){ local target="$1"; local label; label="$(basename "$target")"; echo "MANUAL_PICKER_WAIT=$label"; sleep 2; local seen=0; for second in $(seq 0 180); do
  local state wc sc
  state=$(/usr/bin/osascript - "$PID" <<'OSA'
on run argv
  set targetPid to (item 1 of argv) as integer
  tell application "System Events"
    set ps to every application process whose unix id is targetPid
    if (count of ps) is not 1 then return "0,0"
    set proc to item 1 of ps
    set wc to count of windows of proc
    set sc to 0
    repeat with w in windows of proc
      try
        set sc to sc + (count of sheets of w)
      end try
    end repeat
    return (wc as text) & "," & (sc as text)
  end tell
end run
OSA
  )
  IFS=',' read -r wc sc <<< "$state"
  if [ "${wc:-0}" -gt 1 ] || [ "${sc:-0}" -gt 0 ]; then seen=1; fi
  if [ "$seen" -eq 1 ] && [ "${wc:-0}" -eq 1 ] && [ "${sc:-0}" -eq 0 ]; then echo "MANUAL_PICKER_DONE=$label"; sleep 1; return 0; fi
  sleep 1
done
echo "MANUAL_PICKER_TIMEOUT=$label" >&2; return 88; }'''
manual="new=r'''"+picker+"'''"
v11=v11[:start]+manual+v11[end+4:]
Path(sys.argv[6]).write_text(v11)
PY
chmod +x "$P5" "$P8" "$P11"
echo "MANUAL_SOURCE_FOLDER=$HOME/Desktop/ENDLUME_PHASE2_QA_${GITHUB_RUN_ID}/project"
echo "MANUAL_OUTPUT_FOLDER=$HOME/Desktop/ENDLUME_PHASE2_QA_${GITHUB_RUN_ID}/output"
exec bash "$P11"
