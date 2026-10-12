#!/bin/bash
set -Eeuo pipefail

SRC='scripts/phase4_physical_update_1014.sh'
TMP="${RUNNER_TEMP:?}/phase4_physical_update_1014_vision_runtime.sh"
python3 - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()

start=src.index('# REAL normal ENDLUME updater path. No manual 10.0.14 app copy is allowed here.')
end=src.index('echo UPDATE_DETECTED_10_0_13_TO_10_0_14=PASS\n',start)+len('echo UPDATE_DETECTED_10_0_13_TO_10_0_14=PASS\n')
replacement=r'''# REAL normal ENDLUME updater path. No manual 10.0.14 app copy is allowed here.
# WebKit controls are not reliably exposed through macOS Accessibility on this runner,
# so use Apple Vision OCR on the real foreground window and physically click the
# exact `ОБНОВИТЬ` button. Native updater state.json is the acceptance oracle.
VISION="$ROOT/vision_click.swift"
cat > "$VISION" <<'SWIFT'
import Foundation
import AppKit
import Vision
import CoreGraphics

func fail(_ message:String)->Never { fputs(message+"\n",stderr); exit(2) }
let args=CommandLine.arguments
if args.count < 3 { fail("usage: vision_click.swift TARGET SCREENSHOT") }
let target=args[1].trimmingCharacters(in:.whitespacesAndNewlines).uppercased()
let shot=args[2]
let display=CGMainDisplayID()
guard let image=CGDisplayCreateImage(display) else { fail("SCREEN_CAPTURE_FAILED") }
let rep=NSBitmapImageRep(cgImage:image)
if let png=rep.representation(using:.png,properties:[:]) { try? png.write(to:URL(fileURLWithPath:shot)) }
let req=VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = true
let supported=(try? req.supportedRecognitionLanguages()) ?? []
var langs:[String]=[]
if supported.contains("ru-RU") { langs.append("ru-RU") }
if supported.contains("en-US") { langs.append("en-US") }
if !langs.isEmpty { req.recognitionLanguages=langs }
let handler=VNImageRequestHandler(cgImage:image,options:[:])
do { try handler.perform([req]) } catch { fail("VISION_FAILED: \(error)") }
let observations=(req.results ?? [])
var texts:[String]=[]
var hit:VNRecognizedTextObservation?=nil
for obs in observations {
  guard let cand=obs.topCandidates(1).first else { continue }
  let raw=cand.string.trimmingCharacters(in:.whitespacesAndNewlines)
  if !raw.isEmpty { texts.append(raw) }
  let up=raw.uppercased()
  if up == target || up.replacingOccurrences(of:" ",with:"")==target.replacingOccurrences(of:" ",with:"") { hit=obs; break }
}
print("VISION_TEXT="+texts.joined(separator:" | "))
guard let obs=hit else { print("VISION_TARGET_NOT_FOUND"); exit(3) }
let bb=obs.boundingBox
let pxW=CGFloat(image.width), pxH=CGFloat(image.height)
let screen=NSScreen.screens.first(where:{ $0.frame.contains(NSEvent.mouseLocation) }) ?? NSScreen.main ?? NSScreen.screens[0]
let scale=pxW / max(screen.frame.width,1)
let x=screen.frame.minX + (bb.midX*pxW)/scale
let y=screen.frame.minY + screen.frame.height - (bb.midY*pxH)/scale
let point=CGPoint(x:x,y:y)
print(String(format:"VISION_CLICK target=%@ x=%.1f y=%.1f scale=%.2f",target,x,y,scale))
let src=CGEventSource(stateID:.hidSystemState)
guard let down=CGEvent(mouseEventSource:src,mouseType:.leftMouseDown,mouseCursorPosition:point,mouseButton:.left),
      let up=CGEvent(mouseEventSource:src,mouseType:.leftMouseUp,mouseCursorPosition:point,mouseButton:.left) else { fail("CG_EVENT_FAILED") }
CGWarpMouseCursorPosition(point)
usleep(150000)
down.post(tap:.cghidEventTap)
usleep(120000)
up.post(tap:.cghidEventTap)
print("VISION_CLICKED")
SWIFT

find_live_pid(){
  local name="$1" p cmd
  for p in $(pgrep -x "$name" 2>/dev/null || true); do
    cmd="$(ps -p "$p" -o command= 2>/dev/null || true)"
    case "$cmd" in "$APP/Contents/MacOS/$name"*) printf '%s\n' "$p"; return 0;; esac
  done
  return 1
}
front_app(){
  local pid="$1"
  osascript - "$pid" <<'APPLESCRIPT' >/dev/null 2>&1 || true
on run argv
  set targetPid to (item 1 of argv) as integer
  tell application "System Events"
    try
      set p to first application process whose unix id is targetPid
      set frontmost of p to true
    end try
  end tell
end run
APPLESCRIPT
}

STATE="$HOME/Library/Caches/studio.endlume.desktop/update-center/state.json"
mkdir -p "$ROOT"
if [ -f "$STATE" ]; then cp "$STATE" "$ROOT/update-state-before.json"; fi
BEFORE_STATE_SHA="$(test -f "$STATE" && /usr/bin/shasum -a 256 "$STATE" | awk '{print $1}' || true)"
LAUNCH_EPOCH="$(date +%s)"
open -n "$APP"
APP_PID=''
for i in $(seq 1 45); do
  APP_PID="$(find_live_pid "$OLD_EXE" || true)"
  [ -n "$APP_PID" ] && break
  sleep 1
done
test -n "$APP_PID"
echo PREUPDATE_APP_PID="$APP_PID"

clicked=0
for attempt in $(seq 1 18); do
  # Re-acquire after any normalize/relaunch transition.
  CURRENT_PID="$(find_live_pid "$OLD_EXE" || true)"
  if [ -n "$CURRENT_PID" ]; then APP_PID="$CURRENT_PID"; fi
  if [ -z "$APP_PID" ] || ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "UPDATE_VISION_ATTEMPT=$attempt APP_PROCESS_MISSING"
    sleep 1
    continue
  fi
  front_app "$APP_PID"
  sleep 1
  SHOT="$ROOT/update-modal-$attempt.png"
  # A missing OCR target is an expected retry condition while the startup modal
  # is still appearing. Temporarily remove the inherited rollback ERR trap so a
  # non-zero Vision exit can be inspected/retried instead of rolling back at once.
  trap - ERR
  set +e
  OUT="$(/usr/bin/xcrun swift "$VISION" 'ОБНОВИТЬ' "$SHOT" 2>&1)"; RC=$?
  set -e
  trap on_error ERR
  printf '%s\n' "$OUT" | tee "$ROOT/update-modal-$attempt.vision.txt"
  echo "UPDATE_VISION_ATTEMPT=$attempt RC=$RC PID=$APP_PID"
  if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q 'VISION_CLICKED'; then
    for s in $(seq 1 40); do
      if [ -f "$STATE" ]; then
        NEW_SHA="$(/usr/bin/shasum -a 256 "$STATE" | awk '{print $1}')"
        ST="$(python3 - "$STATE" <<'PY2'
import json,sys
try: print(str(json.load(open(sys.argv[1])).get('state','')).upper())
except Exception: print('')
PY2
)"
        echo "NATIVE_UPDATE_STATE=$ST"
        if [ "$NEW_SHA" != "$BEFORE_STATE_SHA" ] && [[ "$ST" =~ ^(DOWNLOADING|VERIFYING|READY_TO_INSTALL|INSTALLING|RESTART_REQUIRED)$ ]]; then
          clicked=1
          cp "$STATE" "$ROOT/update-state-after-click.json"
          break
        fi
      fi
      sleep 0.5
    done
    [ "$clicked" -eq 1 ] && break
  fi
  sleep 2
done
test "$clicked" -eq 1
echo UPDATE_MODAL_AVAILABLE=PASS
echo UPDATE_UI_INSTALL_CLICK=PASS
echo NATIVE_UPDATER_STATE_STARTED=PASS
echo UPDATE_DETECTED_10_0_13_TO_10_0_14=PASS
'''
src=src[:start]+replacement+src[end:]

restart_start=src.index('# Updater must restart itself as 10.0.14; do not manually launch for this gate.')
restart_end=src.index('echo UPDATER_RESTART=PASS\n',restart_start)+len('echo UPDATER_RESTART=PASS\n')
restart=r'''# Updater is configured with restart_after_install(true). If installation reaches
# RESTART_REQUIRED without relaunching, physically click the real RESTART ENDLUME button.
NEW_EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$INFO")"
RESTART_PID=''
for i in $(seq 1 120); do
  CURRENT_PID="$(find_live_pid "$NEW_EXE" || true)"
  if [ -n "$CURRENT_PID" ] && [ "$CURRENT_PID" != "$APP_PID" ]; then RESTART_PID="$CURRENT_PID"; break; fi
  if [ -f "$STATE" ]; then
    ST="$(python3 - "$STATE" <<'PY2'
import json,sys
try: print(str(json.load(open(sys.argv[1])).get('state','')).upper())
except Exception: print('')
PY2
)"
    if [ "$ST" = 'RESTART_REQUIRED' ] && [ -n "$CURRENT_PID" ]; then
      front_app "$CURRENT_PID"
      SHOT="$ROOT/restart-modal-$i.png"
      trap - ERR
      set +e
      OUT="$(/usr/bin/xcrun swift "$VISION" 'RESTART ENDLUME' "$SHOT" 2>&1)"; RC=$?
      set -e
      trap on_error ERR
      printf '%s\n' "$OUT" | tee "$ROOT/restart-modal-$i.vision.txt"
      if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q 'VISION_CLICKED'; then echo RESTART_UI_CLICK=PASS; fi
    fi
  fi
  sleep 1
done
if [ -z "$RESTART_PID" ]; then
  CURRENT_PID="$(find_live_pid "$NEW_EXE" || true)"
  if [ -n "$CURRENT_PID" ] && [ "$CURRENT_PID" != "$APP_PID" ]; then RESTART_PID="$CURRENT_PID"; fi
fi
test -n "$RESTART_PID"
echo UPDATER_RESTART=PASS
'''
src=src[:restart_start]+restart+src[restart_end:]

Path(sys.argv[2]).write_text(src)
PY
chmod +x "$TMP"
exec /bin/bash "$TMP"
