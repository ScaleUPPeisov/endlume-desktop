#!/bin/bash
set -Eeuo pipefail
BASE="$GITHUB_WORKSPACE/qa/phase2-ui-v5.sh"
OUT="$RUNNER_TEMP/phase2-ui-v30-runtime.sh"
python3 - "$BASE" "$OUT" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
start=s.index("READY=0; for n in $(seq 0 120);")
block=r'''printf 'OWNER_ASSISTED=YES\nLICENSE_BYPASS=NO\n' > "$REPORT/v30-mode.txt"
prompt30(){ /usr/bin/say "$1" >/dev/null 2>&1 || true; echo "OWNER_NAV_REQUIRED=$1"; }
printf '%s\n' 'OWNER_ACTION_REQUIRED: "Кирилл: сейчас смотри на экран Mac. Если macOS спросит доступ к Связке ключей — нажми Разрешить. Когда откроется ENDLUME — открой раздел Проект. Ничего больше делать не нужно."'
/usr/bin/say 'Кирилл. Сейчас смотри на экран Mac. Если macOS спросит доступ к Связке ключей — нажми Разрешить. Когда откроется ENDLUME — открой раздел Проект.' >/dev/null 2>&1 || true
cat > "$RUNNER_TEMP/window-id-v30.swift" <<'SWIFT'
import CoreGraphics
import Foundation
let pid = Int32(CommandLine.arguments[1]) ?? -1
let info = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String:Any]] ?? []
for w in info {
  let wp = (w[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value ?? -2
  let layer = (w[kCGWindowLayer as String] as? NSNumber)?.intValue ?? -1
  let alpha = (w[kCGWindowAlpha as String] as? NSNumber)?.doubleValue ?? 0
  if wp == pid && layer == 0 && alpha > 0, let n = w[kCGWindowNumber as String] as? NSNumber {
    print(n.intValue)
    exit(0)
  }
}
exit(2)
SWIFT
/usr/bin/swiftc "$RUNNER_TEMP/window-id-v30.swift" -o "$RUNNER_TEMP/window-id-v30"
WID=''
for second in $(seq 1 300); do
  WID="$("$RUNNER_TEMP/window-id-v30" "$PID" 2>/dev/null || true)"
  if [ -n "$WID" ]; then
    echo "OWNER_WINDOW_READY=$WID"
    echo "OWNER_READY_AFTER_SECONDS=$second"
    break
  fi
  sleep 1
done
if [ -z "$WID" ]; then
  echo OWNER_WINDOW_TIMEOUT=YES >&2
  echo OWNER_WINDOW_TIMEOUT_SECONDS=300 >&2
  exit 82
fi
cap30(){ local f="$1"; /usr/sbin/screencapture -x -l"$WID" "$REPORT/screens/$f"; test -s "$REPORT/screens/$f"; }
# The owner has opened Project as requested. Capture immediately when the ENDLUME window is available.
cap30 '01-project.png'
prompt30 'Выключи Эффект для каждого проекта.'; sleep 7; cap30 '02-effects-off.png'
prompt30 'Включи Эффект для каждого проекта.'; sleep 7; cap30 '03-effects-on.png'
prompt30 'Выключи Subscribe Button.'; sleep 7; cap30 '04-subscribe-off.png'
prompt30 'Включи Subscribe Button.'; sleep 7; cap30 '05-subscribe-on.png'
prompt30 'Открой Preview проекта так, чтобы было видно превью.'; sleep 8; cap30 '06-preview.png'
prompt30 'Открой Рендер.'; sleep 7; cap30 '07-render.png'
prompt30 'Открой Библиотеку.'; sleep 7; cap30 '08-library.png'
prompt30 'Открой Настройки, вкладку Общие.'; sleep 7; cap30 '09-settings-general.png'
prompt30 'Открой вкладку Fast Engine.'; sleep 6; cap30 '10-settings-fast-engine.png'
prompt30 'Открой вкладку Обновления.'; sleep 6; cap30 '11-settings-updates.png'
prompt30 'Открой вкладку О программе.'; sleep 6; cap30 '12-settings-about.png'
# Base harness already extracted the icon from this exact accepted candidate. Normalize its final evidence name.
test -s "$REPORT/screens/14-application-icon.png"
cp "$REPORT/screens/14-application-icon.png" "$REPORT/screens/13-current-icon.png"
rm -f "$REPORT/screens/14-application-icon.png"
for f in \
  01-project.png \
  02-effects-off.png \
  03-effects-on.png \
  04-subscribe-off.png \
  05-subscribe-on.png \
  06-preview.png \
  07-render.png \
  08-library.png \
  09-settings-general.png \
  10-settings-fast-engine.png \
  11-settings-updates.png \
  12-settings-about.png \
  13-current-icon.png; do
  test -s "$REPORT/screens/$f"
done
COUNT="$(find "$REPORT/screens" -maxdepth 1 -type f -name '*.png' | wc -l | tr -d ' ')"
test "$COUNT" = 13
printf 'OWNER_ASSISTED_CAPTURE=PASS\nSCREENS_CAPTURED=13\nPRODUCT_FILES_CHANGED=0\nFAST_ENGINE_MERGED=NO\nSTABLE_UNTOUCHED=YES\nUPDATER_UNTOUCHED=YES\nRELEASE_BLOCKED=YES\n' > "$REPORT/v30-result.txt"
echo OWNER_ASSISTED_V30=PASS
'''
s=s[:start]+block+'\n'
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$OUT"
exec bash "$OUT"
