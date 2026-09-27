#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP_ROOT="$(mktemp -d /tmp/endlume-837-bootstrap.XXXXXX)"
BASE="$TMP_ROOT/BUILD_ENDLUME_836_LOCAL.command"
PATCHED="$TMP_ROOT/BUILD_ENDLUME_837_REAL.command"
VALIDATOR="$TMP_ROOT/validate-release-8-36.sh"
BOOT_LOG="$TMP_ROOT/bootstrap.log"
BUILD_LOG="$HOME/Desktop/ENDLUME-local-build.log"
cleanup(){ rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true; }
show_failure(){
  local code=$?
  local tail_text=""
  if [[ -f "$BOOT_LOG" ]]; then
    tail_text="$(/usr/bin/tail -n 18 "$BOOT_LOG" 2>/dev/null | /usr/bin/tr '\n' ' ' | /usr/bin/cut -c1-1000 || true)"
  fi
  if [[ -z "$tail_text" && -f "$BUILD_LOG" ]]; then
    tail_text="$(/usr/bin/tail -n 18 "$BUILD_LOG" 2>/dev/null | /usr/bin/tr '\n' ' ' | /usr/bin/cut -c1-1000 || true)"
  fi
  /usr/bin/osascript - "$code" "$tail_text" <<'OSA' >/dev/null 2>&1 || true
on run argv
  set c to item 1 of argv
  set t to item 2 of argv
  if t is "" then set t to "Подробности сохранены в логе обновления ENDLUME."
  display dialog "ENDLUME 8.37 не установлена. Код " & c & return & return & t buttons {"OK"} default button "OK" with icon stop
end run
OSA
  exit "$code"
}
trap cleanup EXIT
trap show_failure ERR
fail(){ echo; echo "❌ ENDLUME 8.37 bootstrap: $1"; return 1; }
exec > >(tee "$BOOT_LOG") 2>&1

echo "ENDLUME Studio 1.0.0-alpha.8.37"
echo "ONE-TIME IN-APP BOOTSTRAP → Remote Update Center"
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

gh api "repos/$REPO/contents/scripts/validate-release-8-36.sh?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$VALIDATOR" || fail "не удалось получить validator 8.36"
python3 - "$VALIDATOR" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text(encoding='utf-8')
required=['DIM="$("$FFPROBE"', 'VBR="$("$FFPROBE"']
missing=[x for x in required if x not in s]
if missing:
    raise SystemExit('8.37 bootstrap: validator path-with-spaces fix missing: '+', '.join(missing))
PY
echo "✅ Path-with-spaces validator подтверждён"

gh api "repos/$REPO/contents/BUILD_ENDLUME_836_LOCAL.command?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить 8.36 base builder"
[[ -s "$BASE" ]] || fail "8.36 base builder пуст"

python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')
src=src.replace('VERSION_EXPECTED="1.0.0-alpha.8.36"','VERSION_EXPECTED="1.0.0-alpha.8.37"')
src=src.replace('echo "❌ ENDLUME 8.36 остановлена ДО замены приложения"','echo "❌ ENDLUME 8.37 остановлена ДО замены приложения"')
src=src.replace('│ 8.36 • 1080p Fidelity Lock • clean first frame            │','│ 8.37 • 1080p Fidelity Lock • Remote Update Center         │')

needle="src=src.replace('SRC=\"$WORK_ROOT/endlume-desktop-8.33\"','SRC=\"$WORK_ROOT/endlume-desktop-8.36\"',1)\n"
if needle not in src:
    raise SystemExit('8.37 bootstrap: 8.36 work-root transform marker missing')
internal="src=src.replace('WORK_ROOT=\"$(choose_work_root)\"','WORK_ROOT=\"$HOME/.endlume-local-builder\"',1)\n"
src=src.replace(needle,needle+internal,1)

apply_marker='python3 scripts/apply-version-8-36.py\n'
addition='''python3 -m py_compile scripts/repair-settings-updater-8-37.py scripts/apply-remote-updater-8-37.py scripts/apply-version-8-37.py
python3 scripts/repair-settings-updater-8-37.py
python3 scripts/apply-remote-updater-8-37.py
python3 scripts/apply-version-8-37.py
'''
if apply_marker not in src:
    raise SystemExit('8.37 bootstrap: apply-version-8-36 marker missing')
src=src.replace(apply_marker,apply_marker+addition,1)

old_stage='''chmod +x scripts/validate-release-8-36.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
new_stage='''chmod +x scripts/validate-release-8-36.sh scripts/validate-release-8-37.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
scripts/validate-release-8-37.sh
node scripts/validate-motion-ui.mjs
'''
if old_stage not in src:
    raise SystemExit('8.37 bootstrap: final validator marker missing')
src=src.replace(old_stage,new_stage,1)

required=[
    'VERSION_EXPECTED="1.0.0-alpha.8.37"',
    'repair-settings-updater-8-37.py',
    'apply-remote-updater-8-37.py',
    'apply-version-8-37.py',
    'validate-release-8-37.sh',
    'assert_no_tauri_appledouble',
    'apply-fidelity-1080p-8-36.py',
    'WORK_ROOT="$HOME/.endlume-local-builder"',
]
for marker in required:
    if marker not in src:
        raise SystemExit(f'8.37 bootstrap incomplete: {marker}')
if "'VERSION_EXPECTED=\"1.0.0-alpha.8.36\"'" in src:
    raise SystemExit('8.37 bootstrap: stale 8.36 required self-gate survived')
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "generated bootstrap syntax failed"
grep -Fq 'VERSION_EXPECTED="1.0.0-alpha.8.37"' "$PATCHED" || fail "8.37 final version gate missing"
grep -Fq 'repair-settings-updater-8-37.py' "$PATCHED" || fail "Settings migration bridge missing"
grep -Fq 'apply-remote-updater-8-37.py' "$PATCHED" || fail "Remote Update Center patch missing"
grep -Fq 'validate-release-8-37.sh' "$PATCHED" || fail "8.37 acceptance gate missing"
grep -Fq 'WORK_ROOT="$HOME/.endlume-local-builder"' "$PATCHED" || fail "bootstrap всё ещё может выбрать внешний диск"
if grep -Fq "'VERSION_EXPECTED=\"1.0.0-alpha.8.36\"'" "$PATCHED"; then fail "в bootstrap осталась старая 8.36 self-check"; fi

echo "✅ Bootstrap 8.37 preflight пройден"
echo "✅ Build workspace закреплён на внутреннем SSD"
echo "✅ Settings updater migration bridge встроен"
echo "✅ Stale 8.36 self-gates отсутствуют"
echo "✅ После установки следующие обновления — готовыми бинарниками из Настроек"
: > "$BUILD_LOG"
/bin/bash "$PATCHED"
