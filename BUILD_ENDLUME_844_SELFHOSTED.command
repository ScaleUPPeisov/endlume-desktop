#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
REAL_GH="/opt/homebrew/bin/gh"
BASE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d /tmp/endlume-844-selfhosted.XXXXXX)"
CORE_PATCHER="$TMP/patch-core-844.py"
REAL_PATCHER="$TMP/patch-real-844.py"

cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.44 SELF-HOSTED: $1"; exit 1; }

[[ -x "$REAL_GH" ]] || fail "gh binary missing"
[[ -n "${GH_TOKEN:-}" ]] || fail "GH_TOKEN missing in self-hosted job"

cat > "$REAL_PATCHER" <<'PY_REAL'
from pathlib import Path
import sys

p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')

# Preserve the proven pinned 8.41 foundation, then replay updater-only 8.42,
# Real CFR 30/60 8.43, and finally add ONLY the local VYRON bridge as 8.44.
needle='scripts/validate-release-8-41.sh "$FFMPEG" "$FFPROBE"\n'
idx=s.find(needle)
if idx < 0:
    raise SystemExit('8.44 REAL: first executable 8.41 gate missing')
at=idx+len(needle)
patch=(
    "for path in scripts/apply-online-updater-8-42.py scripts/apply-version-8-42.py scripts/validate-release-8-42.sh scripts/apply-real-fps-8-43.py scripts/apply-version-8-43.py scripts/validate-real-60fps.sh scripts/apply-vyron-bridge-8-44.py scripts/validate-release-8-44.sh; do\n"
    "  gh api -H 'Accept: application/vnd.github.raw+json' \"/repos/$REPO/contents/$path?ref=release\" > \"$path\" || fail \"cannot fetch $path\"\n"
    "  [[ -s \"$path\" ]] || fail \"$path empty\"\n"
    "done\n"
    "mkdir -p scripts/vyron-bridge-8-40 .github/workflows\n"
    "for path in scripts/vyron-bridge-8-40/vyron_bridge.rs scripts/vyron-bridge-8-40/vyron_bridge_tests.rs scripts/vyron-bridge-8-40/VyronBatchBridge.tsx; do\n"
    "  gh api -H 'Accept: application/vnd.github.raw+json' \"/repos/$REPO/contents/$path?ref=release\" > \"$path\" || fail \"cannot fetch $path\"\n"
    "  [[ -s \"$path\" ]] || fail \"$path empty\"\n"
    "done\n"
    "gh api -H 'Accept: application/vnd.github.raw+json' \"/repos/$REPO/contents/.github/workflows/endlume-self-hosted-release.yml?ref=release\" > .github/workflows/endlume-self-hosted-release.yml || fail \"cannot fetch self-hosted workflow\"\n"
    "python3 -m py_compile scripts/apply-online-updater-8-42.py scripts/apply-version-8-42.py scripts/apply-real-fps-8-43.py scripts/apply-version-8-43.py scripts/apply-vyron-bridge-8-44.py\n"
    "python3 scripts/apply-online-updater-8-42.py\n"
    "python3 scripts/apply-version-8-42.py\n"
    "chmod +x scripts/validate-release-8-42.sh\n"
    "scripts/validate-release-8-42.sh\n"
    "python3 scripts/apply-real-fps-8-43.py\n"
    "python3 scripts/apply-version-8-43.py\n"
    "chmod +x scripts/validate-real-60fps.sh\n"
    "scripts/validate-real-60fps.sh \"$FFMPEG\" \"$FFPROBE\"\n"
    "python3 scripts/apply-vyron-bridge-8-44.py\n"
    "chmod +x scripts/validate-release-8-44.sh\n"
    "scripts/validate-release-8-44.sh \"$FFMPEG\" \"$FFPROBE\"\n"
)
s=s[:at]+patch+s[at:]

# Final identity must be strictly newer than the user's installed 8.43.
s=s.replace('1.0.0-alpha.8.41','1.0.0-alpha.8.44')
s=s.replace('✅ ENDLUME 8.41 signed updater artifact ready','✅ ENDLUME 8.44 signed updater artifact ready')

# Replace only the FINAL Stage 7 block. Historical 8.41/8.42/8.43 gates above
# remain intact; this final gate validates the exact 8.44 tree.
old=(
    'stage "7/10 Проверяю ENDLUME 8.41 • только пункты 1–10" 58\n'
    'chmod +x scripts/validate-release-8-41.sh\n'
    'scripts/validate-release-8-41.sh "$FFMPEG" "$FFPROBE"\n'
    'node scripts/validate-motion-ui.mjs\n'
)
new=(
    'stage "7/10 Проверяю ENDLUME 8.44 • VYRON Bridge + полный 8.43 regression" 58\n'
    'chmod +x scripts/validate-release-8-44.sh\n'
    'scripts/validate-release-8-44.sh "$FFMPEG" "$FFPROBE"\n'
    'gh api -H \'Accept: application/vnd.github.raw+json\' "/repos/$REPO/contents/scripts/validate-motion-ui-8-41.mjs?ref=release" > scripts/validate-motion-ui-8-41.mjs\n'
    'node scripts/validate-motion-ui-8-41.mjs\n'
)
if old not in s:
    raise SystemExit('8.44 REAL: final 8.41 Stage 7 block missing')
s=s.replace(old,new,1)

if 'VERSION_EXPECTED="1.0.0-alpha.8.44"' not in s:
    raise SystemExit('8.44 REAL: final version gate missing')
for marker in ('apply-online-updater-8-42.py','apply-real-fps-8-43.py','apply-vyron-bridge-8-44.py','validate-release-8-44.sh'):
    if marker not in s:
        raise SystemExit('8.44 REAL: missing '+marker)

# Never allow the old wrong 8.40 bridge patch into this chain.
if 'python3 scripts/apply-vyron-bridge-8-40.py' in s:
    raise SystemExit('8.44 REAL: obsolete 8.40 VYRON version patch leaked into build')

p.write_text(s,encoding='utf-8')
print('✅ 8.44 applied after proven 8.41 + updater 8.42 + Real FPS 8.43')
PY_REAL

cat > "$CORE_PATCHER" <<'PY_CORE'
import sys
s=sys.stdin.read()
marker='/bin/bash "$REAL"\n'
pos=s.rfind(marker)
if pos < 0:
    raise SystemExit('8.44 CORE: final REAL execution marker missing')
if s[pos+len(marker):].strip():
    raise SystemExit('8.44 CORE: unexpected commands after final REAL execution')
replacement=(
    'python3 "$ENDLUME_844_REAL_PATCHER" "$REAL"\n'
    '/bin/bash -n "$REAL" || fail "8.44 REAL builder syntax failed"\n'
    'grep -Fq \'VERSION_EXPECTED="1.0.0-alpha.8.44"\' "$REAL" || fail "8.44 final version gate missing"\n'
    'grep -Fq \'apply-real-fps-8-43.py\' "$REAL" || fail "8.43 Real FPS migration missing"\n'
    'grep -Fq \'apply-vyron-bridge-8-44.py\' "$REAL" || fail "8.44 VYRON migration missing"\n'
    'grep -Fq \'validate-release-8-44.sh\' "$REAL" || fail "8.44 final validator missing"\n'
    'echo "✅ ENDLUME 8.44 post-8.43 REAL transformation PASS"\n'
    '/bin/bash "$REAL"\n'
)
s=s[:pos]+replacement
sys.stdout.write(s)
PY_CORE

python3 -m py_compile "$CORE_PATCHER" "$REAL_PATCHER" || fail "8.44 bridge Python syntax failed"

# Compatibility wrapper for the proven historical builders under GitHub Actions.
gh(){
  if [[ "${1:-}" == "auth" && "${2:-}" == "status" ]]; then
    "$REAL_GH" api "/repos/$REPO" --jq .full_name >/dev/null
    return $?
  fi

  local joined=" $* "
  if [[ "$joined" == *'/contents/BUILD_ENDLUME_841_GITHUB.command?ref=release'* ]]; then
    "$REAL_GH" "$@" | python3 "$ENDLUME_844_CORE_PATCHER"
    return $?
  fi

  "$REAL_GH" "$@"
}
export -f gh
export REAL_GH REPO
export ENDLUME_844_CORE_PATCHER="$CORE_PATCHER"
export ENDLUME_844_REAL_PATCHER="$REAL_PATCHER"

"$REAL_GH" api "/repos/$REPO" --jq .full_name >/dev/null || fail "Actions token cannot read ENDLUME repository"

# Fail fast before any expensive build.
for path in scripts/apply-online-updater-8-42.py scripts/apply-version-8-42.py scripts/validate-release-8-42.sh scripts/apply-real-fps-8-43.py scripts/apply-version-8-43.py scripts/validate-real-60fps.sh scripts/apply-vyron-bridge-8-44.py scripts/validate-release-8-44.sh scripts/validate-motion-ui-8-41.mjs; do
  "$REAL_GH" api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/$path?ref=release" > "$TMP/$(basename "$path")" || fail "cannot fetch $path"
  [[ -s "$TMP/$(basename "$path")" ]] || fail "$path empty"
done
python3 -m py_compile "$TMP/apply-online-updater-8-42.py" "$TMP/apply-version-8-42.py" "$TMP/apply-real-fps-8-43.py" "$TMP/apply-version-8-43.py" "$TMP/apply-vyron-bridge-8-44.py" || fail "8.42/8.43/8.44 migration syntax failed"
/bin/bash -n "$TMP/validate-release-8-42.sh" || fail "8.42 validator syntax failed"
/bin/bash -n "$TMP/validate-real-60fps.sh" || fail "8.43 validator syntax failed"
/bin/bash -n "$TMP/validate-release-8-44.sh" || fail "8.44 validator syntax failed"

for path in scripts/vyron-bridge-8-40/vyron_bridge.rs scripts/vyron-bridge-8-40/vyron_bridge_tests.rs scripts/vyron-bridge-8-40/VyronBatchBridge.tsx; do
  "$REAL_GH" api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/$path?ref=release" > "$TMP/$(basename "$path")" || fail "cannot fetch VYRON payload $path"
  [[ -s "$TMP/$(basename "$path")" ]] || fail "VYRON payload empty: $path"
done

chmod +x "$BASE/BUILD_ENDLUME_841_PINNED.command"
/bin/bash -n "$BASE/BUILD_ENDLUME_841_PINNED.command" || fail "8.41 pinned base syntax failed"

echo '✅ ENDLUME 8.44 signed release bridge active'
echo '✅ Proven pinned 8.41 render/audio/size foundation preserved'
echo '✅ 8.42 native signed updater preserved'
echo '✅ 8.43 true CFR30/CFR60 validation preserved'
echo '✅ 8.44 adds only local VYRON Batch Bridge'
echo '✅ Manual render / Effects / Subscribe remain guarded'

exec /bin/bash "$BASE/BUILD_ENDLUME_841_PINNED.command"
