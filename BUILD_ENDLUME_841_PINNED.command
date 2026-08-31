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

# Current orchestration contains the 8.41 release logic. We only change where its
# proven 8.40 foundation and application source are read from.
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/BUILD_ENDLUME_841_GITHUB.command?ref=release" > "$CORE" || fail "cannot fetch 8.41 core builder"
[[ -s "$CORE" ]] || fail "8.41 core builder empty"
/bin/bash -n "$CORE" || fail "8.41 core builder syntax failed"

python3 - "$CORE" "$PATCHED" "$BASE_REF" <<'PY'
from pathlib import Path
import sys

src_path,out_path,base=sys.argv[1:]
s=Path(src_path).read_text(encoding='utf-8')

# Pin the outer 8.40 builder itself.
old_fetch='gh api -H \'Accept: application/vnd.github.raw+json\' "/repos/$REPO/contents/BUILD_ENDLUME_840_DRAGDROP_MAC.command?ref=$BRANCH" > "$BASE"'
new_fetch='gh api -H \'Accept: application/vnd.github.raw+json\' "/repos/$REPO/contents/BUILD_ENDLUME_840_DRAGDROP_MAC.command?ref='+base+'" > "$BASE"'
if old_fetch not in s:
    raise SystemExit('PINNED: 8.40 outer-builder fetch marker missing')
s=s.replace(old_fetch,new_fetch,1)

# Inject pinning into the EXISTING Python block that already transforms the
# generated 8.40 REAL builder to 8.41. No nested triple-quoted Python is created.
marker="p=Path(sys.argv[1])\ns=p.read_text(encoding='utf-8')\n\n# Insert 8.41 immediately after the FIRST executable 8.40 updater gate."
if marker not in s:
    raise SystemExit('PINNED: 8.41 REAL transformation marker missing')

pin_code=(
    "p=Path(sys.argv[1])\n"
    "s=p.read_text(encoding='utf-8')\n"
    "\n"
    "# PINNED 8.40 SOURCE: freeze the application tree, then fetch ONLY the three 8.41 files.\n"
    "base_ref="+repr(base)+"\n"
    "if 'BRANCH=\\\"release\\\"' not in s: raise SystemExit('PINNED: REAL branch marker missing')\n"
    "s=s.replace('BRANCH=\\\"release\\\"','BRANCH=\\\"'+base_ref+'\\\"',1)\n"
    "old_clone='gh repo clone \\\"$REPO\\\" \\\"$SRC\\\" -- --branch \\\"$BRANCH\\\" --single-branch\\ncd \\\"$SRC\\\"\\n'\n"
    "new_clone='gh repo clone \\\"$REPO\\\" \\\"$SRC\\\"\\ngit -C \\\"$SRC\\\" checkout --detach \\\"$BRANCH\\\"\\ncd \\\"$SRC\\\"\\n'\n"
    "if old_clone not in s: raise SystemExit('PINNED: REAL clone marker missing')\n"
    "s=s.replace(old_clone,new_clone,1)\n"
    "fetch41=(\n"
    "  'cd \\\"$SRC\\\"\\n'\n"
    "  'for path in scripts/apply-performance-stability-8-41.py scripts/apply-version-8-41.py scripts/validate-release-8-41.sh; do\\n'\n"
    "  '  gh api -H \\\'Accept: application/vnd.github.raw+json\\\' \\\"/repos/$REPO/contents/$path?ref=release\\\" > \\\"$path\\\" || fail \\\"cannot fetch $path\\\"\\n'\n"
    "  '  [[ -s \\\"$path\\\" ]] || fail \\\"$path empty\\\"\\n'\n"
    "  'done\\n'\n"
    ")\n"
    "if new_clone not in s: raise SystemExit('PINNED: detached clone missing after replacement')\n"
    "s=s.replace(new_clone,new_clone+fetch41,1)\n"
    "\n"
    "# Insert 8.41 immediately after the FIRST executable 8.40 updater gate."
)
s=s.replace(marker,pin_code,1)

Path(out_path).write_text(s,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "pinned wrapper syntax failed"

grep -Fq "$BASE_REF" "$PATCHED" || fail "base pin missing"
grep -Fq 'PINNED 8.40 SOURCE' "$PATCHED" || fail "REAL source pin injection missing"
grep -Fq 'checkout --detach' "$PATCHED" || fail "detached checkout wiring missing"
grep -Fq 'apply-performance-stability-8-41.py' "$PATCHED" || fail "8.41 patch wiring missing"

# Validate the injected inner Python block syntax before any npm/cargo/Tauri work.
python3 - "$PATCHED" <<'PY'
from pathlib import Path
import re,sys
s=Path(sys.argv[1]).read_text(encoding='utf-8')
blocks=re.findall(r"python3 - \"\$REAL\" <<'PY'\n(.*?)\nPY\n",s,re.S)
if not blocks:
    raise SystemExit('PINNED preflight: REAL Python block not found')
for i,b in enumerate(blocks,1):
    compile(b,f'<pinned-real-block-{i}>','exec')
print('✅ PINNED: embedded Python syntax PASS')
PY

echo "✅ ENDLUME 8.41 PINNED preflight"
echo "✅ Base 8.40: $BASE_REF"
echo "✅ Nested triple-quote generator removed"
echo "✅ Embedded Python compiled before build"
echo "✅ Only 8.41 patch/version/gate come from current release"
echo "✅ Mutable release is NOT used as the application base"

/bin/bash "$PATCHED"
