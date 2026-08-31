#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
REAL_GH="/opt/homebrew/bin/gh"
BASE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d /tmp/endlume-843-selfhosted.XXXXXX)"
CORE_PATCHER="$TMP/patch-core-843.py"
REAL_PATCHER="$TMP/patch-real-843.py"

cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.43 SELF-HOSTED: $1"; exit 1; }

[[ -x "$REAL_GH" ]] || fail "gh binary missing"
[[ -n "${GH_TOKEN:-}" ]] || fail "GH_TOKEN missing in self-hosted job"

cat > "$REAL_PATCHER" <<'PY_REAL'
from pathlib import Path
import sys

p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')

# Preserve the proven 8.41 historical gate, then apply 8.42 updater-only migration
# and finally the FPS-only 8.43 migration. Nothing else in the render contract moves.
needle='scripts/validate-release-8-41.sh "$FFMPEG" "$FFPROBE"\n'
idx=s.find(needle)
if idx < 0:
    raise SystemExit('8.43 REAL: first executable 8.41 gate missing')
at=idx+len(needle)
patch=(
    "for path in scripts/apply-online-updater-8-42.py scripts/apply-version-8-42.py scripts/validate-release-8-42.sh scripts/apply-real-fps-8-43.py scripts/apply-version-8-43.py scripts/validate-real-60fps.sh; do\n"
    "  gh api -H 'Accept: application/vnd.github.raw+json' \"/repos/$REPO/contents/$path?ref=release\" > \"$path\" || fail \"cannot fetch $path\"\n"
    "  [[ -s \"$path\" ]] || fail \"$path empty\"\n"
    "done\n"
    "mkdir -p .github/workflows\n"
    "gh api -H 'Accept: application/vnd.github.raw+json' \"/repos/$REPO/contents/.github/workflows/endlume-self-hosted-release.yml?ref=release\" > .github/workflows/endlume-self-hosted-release.yml || fail \"cannot fetch self-hosted workflow\"\n"
    "python3 -m py_compile scripts/apply-online-updater-8-42.py scripts/apply-version-8-42.py scripts/apply-real-fps-8-43.py scripts/apply-version-8-43.py\n"
    "python3 scripts/apply-online-updater-8-42.py\n"
    "python3 scripts/apply-version-8-42.py\n"
    "chmod +x scripts/validate-release-8-42.sh\n"
    "scripts/validate-release-8-42.sh\n"
    "python3 scripts/apply-real-fps-8-43.py\n"
    "python3 scripts/apply-version-8-43.py\n"
    "chmod +x scripts/validate-real-60fps.sh\n"
    "scripts/validate-real-60fps.sh \"$FFMPEG\" \"$FFPROBE\"\n"
)
s=s[:at]+patch+s[at:]

# Final identity is 8.43. 8.42 remains only as an intermediate updater migration.
s=s.replace('1.0.0-alpha.8.41','1.0.0-alpha.8.43')
s=s.replace('✅ ENDLUME 8.41 signed updater artifact ready','✅ ENDLUME 8.43 signed updater artifact ready')

# Replace only the FINAL Stage 7 block. The historical 8.41 gate above remains intact.
old=(
    'stage "7/10 Проверяю ENDLUME 8.41 • только пункты 1–10" 58\n'
    'chmod +x scripts/validate-release-8-41.sh\n'
    'scripts/validate-release-8-41.sh "$FFMPEG" "$FFPROBE"\n'
    'node scripts/validate-motion-ui.mjs\n'
)
new=(
    'stage "7/10 Проверяю ENDLUME 8.43 • Real 60 FPS Output Validation" 58\n'
    'chmod +x scripts/validate-real-60fps.sh\n'
    'scripts/validate-real-60fps.sh "$FFMPEG" "$FFPROBE"\n'
    'gh api -H \'Accept: application/vnd.github.raw+json\' "/repos/$REPO/contents/scripts/validate-motion-ui-8-41.mjs?ref=release" > scripts/validate-motion-ui-8-41.mjs\n'
    'node scripts/validate-motion-ui-8-41.mjs\n'
)
if old not in s:
    raise SystemExit('8.43 REAL: final 8.41 Stage 7 block missing')
s=s.replace(old,new,1)

if 'VERSION_EXPECTED="1.0.0-alpha.8.43"' not in s:
    raise SystemExit('8.43 REAL: final version gate missing')
for marker in ('apply-online-updater-8-42.py','apply-real-fps-8-43.py','validate-real-60fps.sh'):
    if marker not in s:
        raise SystemExit('8.43 REAL: missing '+marker)

p.write_text(s,encoding='utf-8')
print('✅ 8.43 applied after proven 8.41 + updater-only 8.42')
PY_REAL

cat > "$CORE_PATCHER" <<'PY_CORE'
import sys
s=sys.stdin.read()
marker='/bin/bash "$REAL"\n'
pos=s.rfind(marker)
if pos < 0:
    raise SystemExit('8.43 CORE: final REAL execution marker missing')
if s[pos+len(marker):].strip():
    raise SystemExit('8.43 CORE: unexpected commands after final REAL execution')
replacement=(
    'python3 "$ENDLUME_843_REAL_PATCHER" "$REAL"\n'
    '/bin/bash -n "$REAL" || fail "8.43 REAL builder syntax failed"\n'
    'grep -Fq \'VERSION_EXPECTED="1.0.0-alpha.8.43"\' "$REAL" || fail "8.43 final version gate missing"\n'
    'grep -Fq \'apply-real-fps-8-43.py\' "$REAL" || fail "8.43 FPS migration missing"\n'
    'grep -Fq \'validate-real-60fps.sh\' "$REAL" || fail "8.43 FPS validator missing"\n'
    'echo "✅ ENDLUME 8.43 post-8.41 REAL transformation PASS"\n'
    '/bin/bash "$REAL"\n'
)
s=s[:pos]+replacement
sys.stdout.write(s)
PY_CORE

python3 -m py_compile "$CORE_PATCHER" "$REAL_PATCHER" || fail "8.43 bridge Python syntax failed"

# Compatibility wrapper for the proven historical builders under GitHub Actions.
gh(){
  if [[ "${1:-}" == "auth" && "${2:-}" == "status" ]]; then
    "$REAL_GH" api "/repos/$REPO" --jq .full_name >/dev/null
    return $?
  fi

  local joined=" $* "
  if [[ "$joined" == *'/contents/BUILD_ENDLUME_841_GITHUB.command?ref=release'* ]]; then
    "$REAL_GH" "$@" | python3 "$ENDLUME_843_CORE_PATCHER"
    local rc=$?
    return $rc
  fi

  "$REAL_GH" "$@"
}
export -f gh
export REAL_GH REPO
export ENDLUME_843_CORE_PATCHER="$CORE_PATCHER"
export ENDLUME_843_REAL_PATCHER="$REAL_PATCHER"

"$REAL_GH" api "/repos/$REPO" --jq .full_name >/dev/null || fail "Actions token cannot read ENDLUME repository"

for path in scripts/apply-online-updater-8-42.py scripts/apply-version-8-42.py scripts/validate-release-8-42.sh scripts/apply-real-fps-8-43.py scripts/apply-version-8-43.py scripts/validate-real-60fps.sh scripts/validate-motion-ui-8-41.mjs; do
  "$REAL_GH" api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/$path?ref=release" > "$TMP/$(basename "$path")" || fail "cannot fetch $path"
  [[ -s "$TMP/$(basename "$path")" ]] || fail "$path empty"
done
python3 -m py_compile "$TMP/apply-online-updater-8-42.py" "$TMP/apply-version-8-42.py" "$TMP/apply-real-fps-8-43.py" "$TMP/apply-version-8-43.py" || fail "8.42/8.43 migration syntax failed"
/bin/bash -n "$TMP/validate-release-8-42.sh" || fail "8.42 validator syntax failed"
/bin/bash -n "$TMP/validate-real-60fps.sh" || fail "8.43 validator syntax failed"

chmod +x "$BASE/BUILD_ENDLUME_841_PINNED.command"
/bin/bash -n "$BASE/BUILD_ENDLUME_841_PINNED.command" || fail "8.41 pinned base syntax failed"

echo '✅ ENDLUME 8.43 Real 60 FPS validation bridge active'
echo '✅ Proven 8.41 render/audio/size base preserved'
echo '✅ 8.42 native updater migration preserved'
echo '✅ 8.43 changes only final FPS/CFR validation path'

exec /bin/bash "$BASE/BUILD_ENDLUME_841_PINNED.command"
