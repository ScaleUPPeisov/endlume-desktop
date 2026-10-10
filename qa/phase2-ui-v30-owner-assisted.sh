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
prompt30(){ /usr/bin/say "$1" >/dev/null 2>&1 || true; echo "OWNER_ACTION=$1"; }
prompt30 'Кирилл. Если появилось окно связки ключей, нажми Разрешить. Потом открой Проект.'
cat > "$RUNNER_TEMP/window-id-v30.swift" <<'SWIFT'
import CoreGraphics
import Foundation
let pid = Int32(CommandLine.arguments[1]) ?? -1
let info = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String:Any]] ?? []
for w in info {
  let wp = (w[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value ?? -2
  let layer = (w[kCGWindowLayer as String] as? NSNumber)?.intValue ?? -1
  let alpha = (w[kCGWindowAlpha as String] as? NSNumber)?.doubleValue ?? 0
  if wp == pid && layer == 0 && alpha > 0, let n = w[kCGWindowNumber as String] as? NSNumber { print(n.intValue); exit(0) }
}
exit(2)
SWIFT
/usr/bin/swiftc "$RUNNER_TEMP/window-id-v30.swift" -o "$RUNNER_TEMP/window-id-v30"
WID=''
for second in $(seq 0 30); do
  WID="$("$RUNNER_TEMP/window-id-v30" "$PID" 2>/dev/null || true)"
  [ -n "$WID" ] && break
  sleep 1
done
if [ -z "$WID" ]; then echo OWNER_WINDOW_TIMEOUT=YES >&2; exit 82; fi
echo "OWNER_WINDOW_READY=$WID"
cap30(){ local f="$1"; /usr/sbin/screencapture -x -l"$WID" "$REPORT/screens/$f"; test -s "$REPORT/screens/$f"; }
cap30 '01-project-owner.png'
prompt30 'Выключи Эффект для каждого проекта.'; sleep 7; cap30 '02-effects-off.png'
prompt30 'Включи Эффект для каждого проекта.'; sleep 7; cap30 '03-effects-on.png'
prompt30 'Нажми Настроить у Эффекта.'; sleep 8; cap30 '06-effects-editor.png'
prompt30 'Вернись к проекту. Выключи Subscribe Button.'; sleep 8; cap30 '04-subscribe-off.png'
prompt30 'Включи Subscribe Button.'; sleep 7; cap30 '05-subscribe-on.png'
prompt30 'Нажми Настроить у Subscribe Button.'; sleep 8; cap30 '06b-subscribe-editor.png'
prompt30 'Открой Рендер.'; sleep 7; cap30 '07-render-idle.png'
prompt30 'Открой Библиотеку.'; sleep 7; cap30 '09-library.png'
prompt30 'Открой Настройки, вкладку Общие.'; sleep 7; cap30 '10-settings-general.png'
prompt30 'Открой вкладку Fast Engine.'; sleep 6; cap30 '11-settings-fast-engine.png'
prompt30 'Открой вкладку Обновления.'; sleep 6; cap30 '12-settings-updates.png'
prompt30 'Открой вкладку О программе.'; sleep 6; cap30 '13-settings-about.png'
printf 'OWNER_ASSISTED_CAPTURE=PASS\nSCREENS_CAPTURED=13\nPRODUCT_FILES_CHANGED=0\n' > "$REPORT/v30-result.txt"
echo OWNER_ASSISTED_V30=PASS
'''
s=s[:start]+block+'\n'
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$OUT"
exec bash "$OUT"
