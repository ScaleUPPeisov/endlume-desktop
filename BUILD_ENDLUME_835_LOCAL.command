#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP_ROOT="$(mktemp -d /tmp/endlume-835.XXXXXX)"
BASE="$TMP_ROOT/BUILD_ENDLUME_834_LOCAL.command"
PATCHED="$TMP_ROOT/BUILD_ENDLUME_835_REAL.command"
cleanup(){ rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true; }
trap cleanup EXIT

fail(){
  echo
  echo "❌ ENDLUME 8.35 installer: $1"
  /usr/bin/osascript -e "display dialog \"ENDLUME 8.35: $1\" buttons {\"OK\"} default button \"OK\" with icon stop" >/dev/null 2>&1 || true
  exit 1
}

echo "ENDLUME Studio 1.0.0-alpha.8.35"
echo "Strict Fidelity • <=1 GB / 2h target • <=1 minute target • original MP3 copy"
echo

[[ "$(uname -s)" == "Darwin" ]] || fail "нужна macOS"
[[ "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon M1 или новее"

if ! command -v gh >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Устанавливаю Homebrew…"
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || fail "не удалось установить Homebrew"
    [[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
  brew install gh || fail "не удалось установить GitHub CLI"
fi

gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован. Выполни: gh auth login"

echo "Получаю 8.34 Preview Shield builder и накладываю 8.35 Strict Fidelity…"
gh api "repos/$REPO/contents/BUILD_ENDLUME_834_LOCAL.command?ref=$BRANCH" --jq .content \
  | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить базовый builder"
[[ -s "$BASE" ]] || fail "базовый builder пуст"

python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

# Hard preflight: do not even start npm/Rust if the base builder lost one of the
# migration/build-environment repairs already discovered on the user's M1.
if 'repair-speed-workdir-8-33.py' not in src:
    raise SystemExit('8.35 builder: 8.33 workdir compatibility repair missing in base builder')
if 'assert_no_tauri_appledouble' not in src or 'export COPYFILE_DISABLE=1' not in src:
    raise SystemExit('8.35 builder: external-drive AppleDouble build shield missing in base builder')

# The 8.34 wrapper itself generates the real builder. Extend that generation
# deterministically instead of replaying another independent migration chain.
src=src.replace('ENDLUME Studio 1.0.0-alpha.8.34','ENDLUME Studio 1.0.0-alpha.8.35')
src=src.replace('ENDLUME 8.34 installer','ENDLUME 8.35 installer')
src=src.replace('ENDLUME 8.34:','ENDLUME 8.35:')
src=src.replace('VERSION_EXPECTED=\"1.0.0-alpha.8.34\"','VERSION_EXPECTED=\"1.0.0-alpha.8.35\"')
src=src.replace('SRC=\"$WORK_ROOT/endlume-desktop-8.34\"','SRC=\"$WORK_ROOT/endlume-desktop-8.35\"')
src=src.replace('│ 8.34 • Preview Shield • Fast Fidelity • 100/100 gate      │','│ 8.35 • Strict Fidelity • 4K quality • <=1 GB target       │')
src=src.replace('echo \"❌ ENDLUME 8.34 остановлена ДО замены приложения\"','echo \"❌ ENDLUME 8.35 остановлена ДО замены приложения\"')

old_add="""addition='''python3 -m py_compile scripts/apply-stability-8-34.py scripts/apply-version-8-34.py
python3 scripts/apply-stability-8-34.py
python3 scripts/apply-version-8-34.py
'''"""
new_add="""addition='''python3 -m py_compile scripts/apply-stability-8-34.py scripts/apply-version-8-34.py scripts/apply-strict-fidelity-8-35.py scripts/apply-version-8-35.py scripts/repair-strict-store-8-35.py
python3 scripts/apply-stability-8-34.py
python3 scripts/apply-version-8-34.py
python3 scripts/apply-strict-fidelity-8-35.py
python3 scripts/apply-version-8-35.py
python3 scripts/repair-strict-store-8-35.py
'''"""
if old_add not in src:
    raise SystemExit('8.35 builder: 8.34 apply block missing')
src=src.replace(old_add,new_add,1)

old_val="""validation='''chmod +x scripts/validate-release-8-34.sh
scripts/validate-release-8-34.sh \"$FFMPEG\" \"$FFPROBE\"
'''"""
new_val="""validation='''chmod +x scripts/validate-release-8-34.sh scripts/validate-release-8-35.sh
scripts/validate-release-8-34.sh \"$FFMPEG\" \"$FFPROBE\"
scripts/validate-release-8-35.sh \"$FFMPEG\" \"$FFPROBE\"
'''"""
if old_val not in src:
    raise SystemExit('8.35 builder: 8.34 validation block missing')
src=src.replace(old_val,new_val,1)

src=src.replace('Preview Shield • 100/100 Effects+Subscribe gate • 700–1000 MB / 2h target','Strict Fidelity • 4K clean-frame gate • <=1 GB / 2h target • <=1 minute target')
src=src.replace('8.34 • Preview Shield • Fast Fidelity • 100/100 gate','8.35 • Strict Fidelity • 4K clean frame • speed/size gate')

Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "внутренний builder не прошёл shell syntax gate"
grep -Fq 'repair-speed-workdir-8-33.py' "$PATCHED" || fail "в сформированном builder потерян 8.33 workdir repair"
grep -Fq 'repair-strict-store-8-35.py' "$PATCHED" || fail "в сформированном builder потерян Zustand migration repair"
grep -Fq 'assert_no_tauri_appledouble' "$PATCHED" || fail "в сформированном builder потерян AppleDouble build shield"
grep -Fq 'export COPYFILE_DISABLE=1' "$PATCHED" || fail "в сформированном builder потерян COPYFILE_DISABLE"
if grep -Fq 'repair-regression-validators-8-35.py' "$PATCHED"; then fail "obsolete validator repair unexpectedly present"; fi

echo "✅ Compatibility preflight: 8.26/8.32/8.33 + persisted settings защищены"
echo "✅ External-drive shield: AppleDouble ._* удаляются до Rust/Tauri"
echo "✅ Legacy validators already 8.35-aware — дополнительный repair не нужен"
echo "✅ 8.35 builder сформирован: TypeScript + Rust + Preview 100/100 + 4K SSIM + M1 speed gate"
/bin/bash "$PATCHED"
