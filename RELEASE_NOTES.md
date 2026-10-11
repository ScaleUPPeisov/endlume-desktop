# ENDLUME YT Studio PEISOV 10.0.13 — 11.10.2026 · macOS Apple Silicon

- Канонический современный ENDLUME UI и современная иконка сохранены.
- Интегрирован Fast Engine с аппаратным HEVC 1080p60 ускорением для static / periodic / Subscribe профилей.
- Для совместимых MP3 используется packet-preserving clean audio path без лишнего lossy-перекодирования.
- Normalize, Crossfade и неподдерживаемые visual/DSP случаи остаются на безопасном canonical fallback.
- Effects, Subscribe, Render Center, Library, Settings и встроенный updater сохранены.
- Accepted known issue: canonical Preview на frame 299/300 перед 5-second periodic loop boundary может отличаться от phase-correct final export. Исправление запланировано на 10.0.14 (#27).
