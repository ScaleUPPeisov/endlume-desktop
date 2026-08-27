#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP_ROOT="$(mktemp -d /tmp/endlume-834.XXXXXX)"
BASE="$TMP_ROOT/BUILD_ENDLUME_833_LOCAL.command"
PATCHED="$TMP_ROOT/BUILD_ENDLUME_834_REAL.command"
cleanup(){ rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true; }
trap cleanup EXIT

fail(){
  echo
  echo "❌ ENDLUME 8.34 installer: $1"
  /usr/bin/osascript -e "display dialog \"ENDLUME 8.34: $1\" buttons {\"OK\"} default button \"OK\" with icon stop" >/dev/null 2>&1 || true
  exit 1
}

echo "ENDLUME Studio 1.0.0-alpha.8.34"
echo "Preview Shield • 100/100 Effects+Subscribe gate • 700–1000 MB / 2h target"
echo

[[ "$(uname -s)" == "Darwin" ]] || fail "нужна macOS"
[[ "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon M1 или новее"

# The private release channel is accessed through the same authenticated GitHub
# CLI used by ENDLUME's in-app updater. Install gh if it is missing.
if ! command -v gh >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Устанавливаю Homebrew…"
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || fail "не удалось установить Homebrew"
    [[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
  brew install gh || fail "не удалось установить GitHub CLI"
fi

gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован. Открой Terminal, выполни: gh auth login"

echo "Получаю проверенный 8.33 builder и накладываю 8.34 Preview Shield…"
gh api "repos/$REPO/contents/BUILD_ENDLUME_833_LOCAL.command?ref=$BRANCH" --jq .content \
  | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить базовый builder"
[[ -s "$BASE" ]] || fail "базовый builder пуст"

python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

# Version/install workspace only. Do NOT rename 8.33 patch files: they remain
# the validated foundation on top of which 8.34 is applied.
src=src.replace('VERSION_EXPECTED="1.0.0-alpha.8.33"','VERSION_EXPECTED="1.0.0-alpha.8.34"',1)
src=src.replace('echo "❌ ENDLUME 8.33 остановлена ДО замены приложения"','echo "❌ ENDLUME 8.34 остановлена ДО замены приложения"',1)
src=src.replace('SRC="$WORK_ROOT/endlume-desktop-8.33"','SRC="$WORK_ROOT/endlume-desktop-8.34"',1)
src=src.replace('│ 8.33 • SSD workdir • Fast Fidelity • Preview repair       │','│ 8.34 • Preview Shield • Fast Fidelity • 100/100 gate      │',1)

# The historical 8.33 patch is replayed after 8.25 already installed its own
# render_work_dir(app,...) helper. Normalize that helper first; otherwise the
# old patch falsely exits with "render workspace was not moved to output drive".
work_marker='python3 scripts/apply-speed-fidelity-8-33.py\n'
work_repair='''python3 -m py_compile scripts/repair-speed-workdir-8-33.py
python3 scripts/repair-speed-workdir-8-33.py
'''
if work_marker not in src:
    raise SystemExit('8.34 installer: 8.33 speed patch marker missing')
if 'python3 scripts/repair-speed-workdir-8-33.py\n' not in src:
    src=src.replace(work_marker,work_repair+work_marker,1)

apply_marker='python3 scripts/apply-version-8-33.py\n'
addition='''python3 -m py_compile scripts/apply-stability-8-34.py scripts/apply-version-8-34.py
python3 scripts/apply-stability-8-34.py
python3 scripts/apply-version-8-34.py
'''
if apply_marker not in src:
    raise SystemExit('8.34 installer: apply marker missing')
src=src.replace(apply_marker,apply_marker+addition,1)

validate_marker='scripts/validate-release-8-33.sh "$FFMPEG" "$FFPROBE"\n'
validation='''chmod +x scripts/validate-release-8-34.sh
scripts/validate-release-8-34.sh "$FFMPEG" "$FFPROBE"
'''
if validate_marker not in src:
    raise SystemExit('8.34 installer: validation marker missing')
src=src.replace(validate_marker,validate_marker+validation,1)

# Invalidate every historical Live Preview cache before first launch.
cache_marker='/bin/rm -rf "$HOME/Library/Caches/studio.endlume.desktop/render-work" >/dev/null 2>&1 || true\n'
src=src.replace(cache_marker,cache_marker+'/bin/rm -rf "$HOME/Library/Caches/studio.endlume.desktop/live-preview-v5" "$HOME/Library/Caches/studio.endlume.desktop/live-preview-v6" >/dev/null 2>&1 || true\n',1)

# Completion text for this release.
src=src.replace('echo "✅ AppleDouble ._* больше не ломает Effects/Subscribe Preview"',
'''echo "✅ Effects/Subscribe: AppleDouble блокируется по имени И по сигнатуре"
echo "✅ Live Preview v6: старый повреждённый cache не переиспользуется"
echo "✅ Effects+Subscribe stability smoke: 100/100"''',1)

Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "внутренний builder не прошёл syntax gate"

# The real builder performs TypeScript, Rust, audio, size, motion, 100/100
# preview and built-app smoke gates before atomically replacing /Applications.
/bin/bash "$PATCHED"
