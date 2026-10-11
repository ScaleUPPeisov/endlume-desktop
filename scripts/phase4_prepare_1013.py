#!/usr/bin/env python3
from pathlib import Path
import re

BASE = "e4a07972b1566ed73b11c4eb758d59f4dc839e71"
VERSION = "10.0.13"


def replace_exact(path: str, old: str, new: str, count: int | None = None) -> None:
    p = Path(path)
    s = p.read_text()
    n = s.count(old)
    if count is not None and n != count:
        raise SystemExit(f"{path}: expected {count} matches for {old!r}, got {n}")
    if n < 1:
        raise SystemExit(f"{path}: missing {old!r}")
    p.write_text(s.replace(old, new))


replace_exact("package.json", '"version": "10.0.11"', '"version": "10.0.13"', 1)

p = Path("package-lock.json")
s = p.read_text()
old = '"version": "10.0.11"'
if s.count(old) < 2:
    raise SystemExit("package-lock.json: expected top/root 10.0.11 versions")
p.write_text(s.replace(old, '"version": "10.0.13"', 2))

p = Path("src-tauri/Cargo.toml")
s = p.read_text()
s2, n = re.subn(r'(\[package\][\s\S]*?\nversion\s*=\s*")10\.0\.11(")', r'\g<1>10.0.13\2', s, count=1)
if n != 1:
    raise SystemExit("Cargo.toml package version replacement failed")
p.write_text(s2)

p = Path("src-tauri/Cargo.lock")
s = p.read_text()
s2, n = re.subn(r'(\[\[package\]\]\nname = "endlume"\nversion = ")10\.0\.11(")', r'\g<1>10.0.13\2', s, count=1)
if n != 1:
    raise SystemExit("Cargo.lock endlume version replacement failed")
p.write_text(s2)

replace_exact("src-tauri/tauri.conf.json", '"version": "10.0.11"', '"version": "10.0.13"', 1)

p = Path("src/components/ReleaseHistory.tsx")
s = p.read_text()
anchor = "const releases:Release[]=[\n"
if s.count(anchor) != 1:
    raise SystemExit("ReleaseHistory anchor mismatch")
if "version:'10.0.13'" in s:
    raise SystemExit("10.0.13 already present")
block = """  {version:'10.0.13',date:'11.10.2026',current:true,title:'Fast Engine • Modern ENDLUME • HEVC Acceleration',items:[
    'Восстановлен канонический современный интерфейс ENDLUME и современная фирменная иконка без отката продукта к старой оболочке.',
    'Fast Engine интегрирован в канонический ENDLUME: static, periodic Effects и Subscribe-проекты получают сверхбыстрый HEVC 1080p60 render path.',
    'Для совместимых MP3 сохранён чистый packet-preserving audio path без лишнего перекодирования; полные треки и порядок музыки сохраняются.',
    'DSP-сценарии Normalize, Crossfade и неподдерживаемые visual-конфигурации безопасно используют проверенный canonical fallback.',
    'Effects и Subscribe сохранены, включая timing, animation, position/scale и повторения; Render Center, Library и Settings сохранены без функциональных изменений.',
    'Известное ограничение 10.0.13: canonical Preview может отличаться на последнем кадре перед границей 5-секундного periodic loop; финальный export остаётся phase-correct.'
  ]},
"""
s = s.replace(anchor, anchor + block, 1)
old_current = "{version:'10.0.10',date:'02.10.2026',current:true"
new_current = "{version:'10.0.10',date:'02.10.2026',current:false"
if s.count(old_current) != 1:
    raise SystemExit("10.0.10 current marker mismatch")
p.write_text(s.replace(old_current, new_current, 1))

Path("RELEASE_NOTES.md").write_text("""# ENDLUME YT Studio PEISOV 10.0.13 — 11.10.2026 · macOS Apple Silicon

- Канонический современный ENDLUME UI и современная иконка сохранены.
- Интегрирован Fast Engine с аппаратным HEVC 1080p60 ускорением для static / periodic / Subscribe профилей.
- Для совместимых MP3 используется packet-preserving clean audio path без лишнего lossy-перекодирования.
- Normalize, Crossfade и неподдерживаемые visual/DSP случаи остаются на безопасном canonical fallback.
- Effects, Subscribe, Render Center, Library, Settings и встроенный updater сохранены.
- Accepted known issue: canonical Preview на frame 299/300 перед 5-second periodic loop boundary может отличаться от phase-correct final export. Исправление запланировано на 10.0.14 (#27).
""")

Path("release").mkdir(exist_ok=True)
Path("release/ENDLUME_10.0.13_RELEASE.md").write_text("""# ENDLUME 10.0.13 Release Record

- Release version: 10.0.13
- Source engine head: `e4a07972b1566ed73b11c4eb758d59f4dc839e71`
- Canonical base: `3f06c7329bd3821bc160e6d88c5b294fc0d82c2b`
- Fast Engine source: `a7a399e83de8b9248e2065c6dda1f9079ded6565`
- Phase 3 source artifact: `11677270291`
- Phase 3 final diagnostic evidence: `11693338342`
- Owner authorization: RELEASE 10.0.13 APPROVED

## Accepted physical qualification

- Static 3h: 2.5135 s, 437.255 MB, HEVC 1080p60, MP3 packet-copy, decode/seek/DTS PASS.
- Periodic 3h: 5.8622 s, 437.279 MB, phase/seam/decode/seek/DTS PASS.
- Subscribe 3h: 3.1270 s, 437.394 MB, timing/decode/seek/DTS PASS.
- Combined: 22.180 s, informational performance warning only.
- Normalize/Crossfade/Unsupported visual fallbacks: PASS.

## Accepted known issue

`KNOWN_PREVIEW_ONLY_PERIODIC_BOUNDARY_ISSUE`: canonical Preview frame 299/300 at 4.983333333 s has MAE 8.5345293, while Fast-render output matches expected source frame 299 at MAE ~0.03263. Export is phase-correct. Follow-up: #27 for 10.0.14.
""")

print("PHASE4_METADATA_PATCH_READY=YES")
