#!/bin/bash
set -Eeuo pipefail

BASE_REF="4c1fcc30f5b8ef270484b5c61f8e26120d852b99"
REPO="ScaleUPPeisov/endlume-desktop"
TMP="$(mktemp -d /tmp/endlume-841-pinned.XXXXXX)"
CORE="$TMP/BUILD_ENDLUME_841_GITHUB.command"
PATCHED="$TMP/BUILD_ENDLUME_841_GITHUB_PINNED.command"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.41 PINNED: $1"; exit 1; }

export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME COPYFILE_DISABLE=1 COPY_EXTENDED_ATTRIBUTES_DISABLE=1

[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI missing"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI not authenticated"

# Fetch current 8.41 orchestration, but pin its proven 8.40 foundation.
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/BUILD_ENDLUME_841_GITHUB.command?ref=release" > "$CORE" || fail "cannot fetch 8.41 core builder"
[[ -s "$CORE" ]] || fail "8.41 core builder empty"

python3 - "$CORE" "$PATCHED" "$BASE_REF" <<'PY'
from pathlib import Path
import sys
src,out,base=sys.argv[1:]
s=Path(src).read_text(encoding='utf-8')

# 1) Fetch the known-good 8.40 outer builder from the exact parent commit.
old='gh api -H \'Accept: application/vnd.github.raw+json\' "/repos/$REPO/contents/BUILD_ENDLUME_840_DRAGDROP_MAC.command?ref=$BRANCH" > "$BASE"'
new=f'gh api -H \'Accept: application/vnd.github.raw+json\' "/repos/$REPO/contents/BUILD_ENDLUME_840_DRAGDROP_MAC.command?ref={base}" > "$BASE"'
if old not in s: raise SystemExit('PINNED: 8.40 fetch marker missing')
s=s.replace(old,new,1)

# 2) After the 8.40 REAL builder is generated, force its source clone to the
# exact 8.40 commit and inject only the 8.41 patch/version/gate from release.
marker='''/bin/bash "$GEN"\n[[ -s "$REAL" ]] || fail "8.40 proven REAL builder was not generated"\n'''
if marker not in s: raise SystemExit('PINNED: generated REAL marker missing')
insert=f'''/bin/bash "$GEN"\n[[ -s "$REAL" ]] || fail "8.40 proven REAL builder was not generated"\npython3 - "$REAL" "{base}" <<'PY_PIN'\nfrom pathlib import Path\nimport sys\np=Path(sys.argv[1]); base=sys.argv[2]; x=p.read_text(encoding='utf-8')\nx=x.replace('BRANCH="release"',f'BRANCH="{{base}}"',1)\nold='gh repo clone "$REPO" "$SRC" -- --branch "$BRANCH" --single-branch\\ncd "$SRC"\\n'\nnew='gh repo clone "$REPO" "$SRC"\\ngit -C "$SRC" checkout --detach "$BRANCH"\\ncd "$SRC"\\n'\nif old not in x: raise SystemExit('PINNED: clone marker missing')\nx=x.replace(old,new,1)\n# The pinned 8.40 commit intentionally does not contain 8.41 files. Fetch only\n# these three current files after checkout; everything else stays frozen.\ncd='cd "$SRC"\\n'\nfetch='''cd "$SRC"\nfor path in scripts/apply-performance-stability-8-41.py scripts/apply-version-8-41.py scripts/validate-release-8-41.sh; do\n  gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/$path?ref=release" > "$path" || fail "cannot fetch $path"\n  [[ -s "$path" ]] || fail "$path empty"\ndone\n'''\nx=x.replace(cd,fetch,1)\np.write_text(x,encoding='utf-8')\nPY_PIN\n'''
s=s.replace(marker,insert,1)

Path(out).write_text(s,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "pinned wrapper syntax failed"
grep -Fq "$BASE_REF" "$PATCHED" || fail "base pin missing"
grep -Fq 'git -C "$SRC" checkout --detach "$BRANCH"' "$PATCHED" || fail "detached checkout pin missing"
grep -Fq 'apply-performance-stability-8-41.py' "$PATCHED" || fail "8.41 patch injection missing"

echo "✅ ENDLUME 8.41 PINNED preflight"
echo "✅ Base 8.40: $BASE_REF"
echo "✅ Only 8.41 patch/version/gate are taken from current release"
echo "✅ No mutable release source is used as the application base"
/bin/bash "$PATCHED"
