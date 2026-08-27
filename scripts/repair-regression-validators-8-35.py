from pathlib import Path
import re


def must(cond: bool, msg: str):
    if not cond:
        raise SystemExit(f"8.35 validator repair: {msg}")

# 8.33 regression is intentionally run after the 8.34/8.35 hardening patches.
# It must validate preserved behaviour, not reject a newer package version.
p = Path('scripts/validate-release-8-33.sh')
s = p.read_text(encoding='utf-8')
old = '''# This regression gate may run after 8.34 hardening has already bumped the
# package version. Accept both the native 8.33 stage and the superseding 8.34.
if grep -Fq '\"version\": \"1.0.0-alpha.8.33\"' \"$PKG\"; then
  pass 'package version is 8.33 for native regression stage'
elif grep -Fq '\"version\": \"1.0.0-alpha.8.34\"' \"$PKG\"; then
  pass 'package version is 8.34; running backward 8.33 regression gate after hardening'
else
  fail 'package version is neither 8.33 nor 8.34'
fi
'''
new = '''# This is a backward-compatibility regression gate. Newer 8.x releases are
# valid as long as the 8.33 invariants above are still present.
if grep -Eq '\"version\": \"1\\.0\\.0-alpha\\.8\\.(33|34|35)\"' \"$PKG\"; then
  pass 'package version is compatible with the 8.33 backward regression gate'
else
  fail 'package version is outside the supported 8.33/8.34/8.35 regression range'
fi
'''
if old in s:
    s = s.replace(old, new, 1)
elif '8.33/8.34/8.35 regression range' not in s:
    # Fallback for slight wording drift.
    pat = re.compile(r"# This regression gate may run after 8\.34.*?\nfi\n", re.S)
    s, n = pat.subn(new, s, count=1)
    must(n == 1, '8.33 version block not found')
p.write_text(s, encoding='utf-8')

# 8.34 Preview Shield is also deliberately re-run after Strict Fidelity bumps
# the package to 8.35. Accept 8.35 while keeping all actual shield checks.
p = Path('scripts/validate-release-8-34.sh')
s = p.read_text(encoding='utf-8')
old_line = "grep -Fq '\"version\": \"1.0.0-alpha.8.34\"' \"$PKG\" || fail 'package version is not 8.34'"
new_block = '''if grep -Eq '\"version\": \"1\\.0\\.0-alpha\\.8\\.(34|35)\"' \"$PKG\"; then
  pass 'package version is compatible with the 8.34 Preview Shield regression gate'
else
  fail 'package version is neither 8.34 nor 8.35'
fi'''
if old_line in s:
    s = s.replace(old_line, new_block, 1)
elif '8.34 Preview Shield regression gate' not in s:
    must(False, '8.34 version check not found')
p.write_text(s, encoding='utf-8')

print('ENDLUME: legacy 8.33/8.34 validators normalized for 8.35 regression replay')
