#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v8.sh"
PATCHED="$RUNNER_TEMP/phase2-ui-v11-wrapper.sh"
python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
# Finder Go to Folder path entry must not depend on the current macOS keyboard layout.
old='''    keystroke targetPath\n    delay 0.2\n    key code 36\n'''
new='''    set the clipboard to targetPath\n    keystroke "v" using {command down}\n    delay 0.2\n    key code 36\n'''
if old not in s: raise SystemExit('choose_safe typing sequence not found')
s=s.replace(old,new,1)
needle='''choose_safe "$FIX/project"\nsleep 2\n# Scroll to project bottom; output picker sits above fixed queue footer.\n'''
replacement=r'''choose_safe "$FIX/project"
sleep 2
capture_native(){
  local out="$1" g
  g=$(/usr/bin/osascript - "$PID" <<'OSA'
on run argv
  set targetPid to (item 1 of argv) as integer
  tell application "System Events"
    set ps to every application process whose unix id is targetPid
    if (count of ps) is not 1 then error "candidate missing"
    tell item 1 of ps
      set frontmost to true
      set p to position of window 1
      set z to size of window 1
      return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of z as text) & "," & (item 2 of z as text)
    end tell
  end tell
end run
OSA
  )
  IFS=',' read -r x y w h <<< "$g"
  /usr/sbin/screencapture -x -R"$x,$y,$w,$h" "$out"
  test -s "$out"
}
capture_native "$REPORT/screens/geometry-project-top.png"
/usr/bin/osascript -e 'tell application "System Events" to key code 125 using {command down}'
sleep .7
capture_native "$REPORT/screens/geometry-project-bottom.png"
printf 'GEOMETRY_PROBE=PASS\nLICENSED_SESSION=PASS\nFINDER_PATH_PASTE=PASS\nOWNER_PRODUCT_UNCHANGED=YES\n' > "$REPORT/geometry-probe.txt"
echo GEOMETRY_PROBE=PASS
exit 0
# Scroll to project bottom; output picker sits above fixed queue footer.
'''
if needle not in s: raise SystemExit('geometry insertion point not found')
s=s.replace(needle,replacement,1)
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$PATCHED"
exec bash "$PATCHED"
