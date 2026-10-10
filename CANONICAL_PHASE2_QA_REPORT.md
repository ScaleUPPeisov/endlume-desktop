# ENDLUME Canonical Product Reconstruction — Phase 2 QA Report

## Final status

**PHASE 2 FULL UI ACCEPTANCE: PASS**

**CANONICAL PRODUCT BASE: GREEN**

Accepted product source:

`3f06c7329bd3821bc160e6d88c5b294fc0d82c2b`

Accepted QA application binary SHA-256:

`4d208994181c5ca21b20c2e01dd06bda25e82a16bb1405379e79cc4da3026436`

Accepted QA application ZIP SHA-256:

`0b374fffa3dbf057620d2f3a5b7919306df474767494ef2daead3bb319afb250`

Owner production application SHA-256 after manual QA:

`2df386c00da09e76f90218061e7f57ccfba2249a654ec1262b06000b322eb9d7`

Date: `2026-10-10`

Owner machine: `MacBook-Air-Kirill`

This report does **not** declare a stable release and does **not** merge Fast Engine.

## Product-tree immutability

Comparison from canonical product commit `3f06c7329bd3821bc160e6d88c5b294fc0d82c2b` to the final Phase 2 QA branch head before this report update contains only:

- `.github/workflows/**` QA workflow files
- `qa/**` QA harness files
- canonical reconstruction / QA markdown documentation

No `src/**`, `src-tauri/**`, CSS, icon asset, ReleaseHistory implementation, Project UI, Effects UI, Subscribe UI, Render Center UI, Library UI, or Settings visual-layer product source changed during Phase 2 QA.

Fast Engine work remains unmerged.

## Source contract gate

Workflow run:

`38030777284`

Result: **PASS**

Verified:

- canonical reconstruction boundary
- exact 18-path reconstructed product delta
- modern application icon present
- rejected old infinity icon absent
- October/current 10.0.x release history present
- modern Render Center contract present
- Effects / Subscribe UI contract present
- Fast Engine merge absent

Markers:

- `CANONICAL_PRODUCT_DELTA_EXACT=PASS`
- `FAST_ENGINE_MERGED=NO`

## TypeScript and Rust regression gate

Workflow run:

`38030777284`

Result: **PASS**

Executed:

- `npm ci`
- `npm run check`
- `npm run build`
- `cargo test`
- `cargo check --target aarch64-apple-darwin`

Rust tests:

- 23 passed
- 0 failed

Marker:

`TYPESCRIPT_RUST_REGRESSION=PASS`

## Production-like Apple Silicon app build

Workflow run:

`38030777284`

Result: **PASS**

Verified:

- macOS ARM64 application bundle built
- bundle identifier `studio.endlume.desktop`
- QA candidate version `10.0.11`
- Apple Silicon `arm64` executable
- codesign verification passed

Marker:

`ARM64_BUILD=PASS`

## 12-track Effects + Subscribe product E2E

Workflow run:

`38030777284`

Result: **PASS**

Exact E2E report:

```json
{"duration":7200.004,"effects":true,"encoder":"hevc_videotoolbox","fastPath":true,"mib":320.76484966278076,"sizeGate":"nonempty-only; Phase 2 has no release-size target","status":"PASS","subscribe":true,"tracks":12,"wallSeconds":15.39311125}
```

Verified:

- 12 MP3 tracks
- Effects exercised
- Subscribe exercised
- about 2 hours output duration
- 1920×1080
- 60 FPS
- HEVC via `hevc_videotoolbox`
- non-empty output
- fast product path active

Marker:

`TWELVE_TRACK_EFFECTS_SUBSCRIBE_E2E=PASS`

## Accepted QA artifact

Artifact:

- artifact ID: `11661604955`
- artifact name: `ENDLUME-CANONICAL-GOOD-PRODUCT-QA`
- archive digest: `sha256:20b280f648cf4b9725e324a9e0e3f7384cbb643702dc749f1d4ed702497ab1bc`
- application ZIP SHA-256: `0b374fffa3dbf057620d2f3a5b7919306df474767494ef2daead3bb319afb250`
- application binary SHA-256: `4d208994181c5ca21b20c2e01dd06bda25e82a16bb1405379e79cc4da3026436`

The final owner visual acceptance used this same accepted artifact. No rebuild was performed.

## Licensed owner foreground acceptance

Earlier automated GUI attempts were blocked by macOS Keychain / Accessibility / window-discovery behavior. Those automation failures were not treated as product failures.

The final Phase 2 UI gate intentionally switched to manual owner foreground acceptance on the physical owner Mac.

The candidate was prepared at:

`/Volumes/ENDLUME_CANONICAL_QA/ENDLUME-CANONICAL-GOOD-PRODUCT-QA.app`

Before launch, the owner terminal physically verified:

- ZIP SHA-256 = `0b374fffa3dbf057620d2f3a5b7919306df474767494ef2daead3bb319afb250`
- binary SHA-256 = `4d208994181c5ca21b20c2e01dd06bda25e82a16bb1405379e79cc4da3026436`
- bundle ID = `studio.endlume.desktop`
- version = `10.0.11`
- codesign = PASS

The app was launched manually by the owner from normal Terminal, outside GitHub Actions GUI automation.

Licensed session: **PASS**

Evidence included the normal licensed product UI and Settings → General showing ENDLUME activated. No QA code or workflow introduced a license bypass.

## Physical multi-screen UI acceptance

Owner-supplied physical screenshots on `2026-10-10` were reviewed for the accepted candidate.

### Project

**PASS**

Verified modern October product UI including:

- Project top navigation
- 1080p / 60 FPS / H.265 controls
- loop modes
- duration / bitrate controls
- current layout and styling

### Effects OFF / ON

**PASS**

Both states were physically shown in Project UI.

### Effects editor

**PASS**

Verified:

- modern Effects editor
- library effects visible
- live source preview
- chromakey controls
- similarity / blend / despill controls
- positioning / sizing controls
- effect enabled state

### Subscribe OFF / ON

**PASS**

Both states were physically shown in Project UI.

### Subscribe editor

**PASS**

Verified:

- live preview
- Subscribe overlay visibly rendered as `SUBSCRIBED`
- chromakey controls
- interval scheduling controls
- position / size controls
- active Subscribe state

### Live Preview

**PASS**

Verified with an actual source image loaded. Effects and Subscribe were visibly composited in preview.

### Render Center

**PASS**

Verified modern current Render Center in both idle and completed-job states.

A physical render completed with:

- `1 из 1`
- `100.00%`
- `0 ошибок`
- render time `0:10`
- output size `407.5 МБ`
- `8` audio tracks
- engine `hevc_videotoolbox`
- Effects pipeline stages completed
- Subscribe pipeline stage completed
- final FFprobe validation completed

Old Render Center: **not present in accepted UI**.

### Library

**PASS**

Verified current Library UI with persisted Effects assets visible.

### Settings → General

**PASS**

Verified licensed state: `ENDLUME активирована`.

### Settings → Fast Engine

**PASS**

Verified the current Settings tab and benchmark surface. This is UI acceptance only; Fast Engine source was not merged into the canonical product base during Phase 2.

### Settings → Updates

**PASS**

Verified current October/current 10.0.x release history including entries such as:

- 10.0.10
- 10.0.9
- 10.0.3
- 10.0.2
- 10.0.1
- 10.0.0

Old alpha entries appear only as historical older entries.

Markers:

- `OCTOBER_HISTORY=PASS`
- `ALPHA_ONLY_CURRENT_HISTORY=NO`

The isolated QA-volume updater attempt displayed `Cross-device link (os error 18)` when trying to bridge 10.0.11 → 10.0.12. No update installation completed, and this was not treated as a Phase 2 product-UI failure because the gate intentionally tested the fixed accepted 10.0.11 candidate from an isolated mounted volume.

### Settings → About

**PASS**

Verified:

- ENDLUME YT Studio PEISOV
- version `10.0.11`
- Apple Silicon M1+
- Rust + FFmpeg
- Tauri 2

### Application / Dock icon

**PASS**

The owner physically showed the mounted QA application in Dock with the current ENDLUME cyan/magenta emblem. The rejected old infinity icon was not present.

## Owner / stable safety boundary

After manual QA, the owner physically re-hashed the installed production application:

`/Applications/ENDLUME YT Studio PEISOV.app`

Result:

`2df386c00da09e76f90218061e7f57ccfba2249a654ec1262b06000b322eb9d7`

This exactly matches the pre-QA owner production application binary SHA-256.

Therefore:

- `OWNER_APPLICATION_REPLACED=NO`
- owner production binary unchanged
- no stable publication performed
- live updater package / manifest untouched
- no OAuth reset action performed
- no Google / YouTube logout action performed
- no license bypass added
- no Fast Engine merge performed

## Final Phase 2 acceptance decision

All required Phase 2 product gates are accepted:

1. source reconstruction contract — PASS
2. TypeScript / Rust regression — PASS
3. Apple Silicon application build — PASS
4. 12-track Effects + Subscribe product E2E — PASS
5. isolated physical launch — PASS
6. licensed owner foreground session — PASS
7. Project — PASS
8. Effects OFF / ON — PASS
9. Effects editor — PASS
10. Subscribe OFF / ON — PASS
11. Subscribe editor — PASS
12. Live Preview — PASS
13. Render Center idle / completed render — PASS
14. Library — PASS
15. Settings General — PASS
16. Settings Fast Engine — PASS
17. Settings Updates — PASS
18. Settings About — PASS
19. October/current ReleaseHistory — PASS
20. modern application icon — PASS
21. owner production application immutability — PASS

Final markers:

- `PHASE_2_FULL_UI_ACCEPTANCE=PASS`
- `CANONICAL_PRODUCT_BASE=GREEN`
- `PHASE_2_ACCEPTED_PRODUCT_SHA=3f06c7329bd3821bc160e6d88c5b294fc0d82c2b`
- `FAST_ENGINE_MERGED=NO`
- `STABLE_UNTOUCHED=YES`
- `UPDATER_UNTOUCHED=YES`
- `RELEASE_BLOCKED=YES`

## Next authorized step

Only after this accepted Phase 2 gate may Phase 3 begin.

Phase 3 target:

Semantic transplant of Fast Engine from:

`a7a399e83de8b9248e2065c6dda1f9079ded6565`

into:

`3f06c7329bd3821bc160e6d88c5b294fc0d82c2b`

Protection rule:

Fast Engine transplant must not modify `src/pages/**`, `src/components/**`, CSS, icons, ReleaseHistory, Settings visual layer, Project UI, Effects UI, Subscribe UI, Render Center UI, or Library UI unless a backend API compatibility change is absolutely required and separately justified.

**Phase 3 was not started by this Phase 2 acceptance update.**
