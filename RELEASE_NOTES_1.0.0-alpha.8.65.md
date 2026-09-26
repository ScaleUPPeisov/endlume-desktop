# ENDLUME 1.0.0-alpha.8.65 — Dual-platform hotfix

Date: 26.09.2026

## What changed

- Successful renders now persist exact `resultPath` and `resultBytes` directly from `RenderOutcome`; terminal queue snapshots no longer depend on guessing the newest filename.
- Frontend terminal-state merges preserve valid result path/size/bitrate/encoder values when a later snapshot carries null fields.
- Plain one-image jobs without active Effects/Subscribe now enter the 30-frame physical still + zero-copy sample-table path instead of encoding a 12–60 second strict visual master.
- One-image fast path skips the redundant physical concat process when only one clip exists.
- Render summary hides duplicate compatibility timing aliases.
- Homer startup splash appears on every launch for at least ~1.15 s and displays the full product name: ENDLUME YT Studio PEISOV • Long Video Engine.
- Original MP3 packet-copy, whole-song duration, HEVC 1920×1080/60, updater signature verification and SHA-256 gate remain required.

## Release targets

- Windows 10/11 x64
- macOS Apple Silicon

## Release gate

Stable promotion is allowed only after source/queue contracts, physical one-image render validation, frontend/Rust regression, platform builds, signatures, SHA-256 checks and public updater verification complete successfully.
