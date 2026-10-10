# ENDLUME Canonical Product Reconstruction — Phase 2 QA Report

## Status

**CANONICAL PRODUCT CANDIDATE: GREEN ON SOURCE / BUILD / RENDER / ISOLATED LAUNCH**

**FULL LICENSED MULTI-SCREEN GUI ACCEPTANCE: BLOCKED — no authorized QA GUI license/session is available on the clean hosted macOS runner. No license bypass was added.**

This report does **not** declare a stable release and does **not** modify the owner installation.

## Canonical product source

Canonical reconstructed product tree commit:

`3f06c7329bd3821bc160e6d88c5b294fc0d82c2b`

Reconstruction branch:

`release-fix/endlume-10.0.13-canonical-product-reconstruction`

The product delta is exactly the audited reconstruction described in:

- `CANONICAL_PRODUCT_DELTA_MAP.md`
- `CANONICAL_GOOD_PRODUCT_MATRIX.md`

Fast Engine work is not merged into this candidate.

## Product-tree immutability after reconstruction

Comparison from the canonical product tree commit `3f06c732...` to QA head `7941ef1c...` contains only:

- `.github/workflows/endlume-1013-canonical-product-launch-only.yml`
- `.github/workflows/endlume-1013-canonical-product-qa.yml`
- `CANONICAL_GOOD_PRODUCT_MATRIX.md`
- `CANONICAL_PRODUCT_DELTA_MAP.md`

No product source file changed during QA/infrastructure fixes.

## Source contract gate

Workflow run:

`38030777284`

Source contract job:

`114151076816`

Result: **PASS**

Verified:

- canonical reconstruction boundary
- exact 18-path final product delta
- 15 exact late-product paths from `8a0b29b0468b5e665705e20c6a8635ca4c73ba90`
- 3 exact visual paths from `af7883d`
- modern application icon present
- rejected old infinity icon absent
- October release history/changelog present
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

Note: npm audit reported one high-severity dependency warning. It was not changed or falsely reported as fixed by this reconstruction pass.

## Production-like Apple Silicon app build

Workflow run:

`38030777284`

Result: **PASS**

Verified:

- macOS ARM64 application bundle built
- bundle identifier `studio.endlume.desktop`
- reconstructed application version `10.0.11`
- Apple Silicon `arm64` executable
- codesign verification passed

Marker:

`ARM64_BUILD=PASS`

This is a QA reconstruction build, not a stable release publication.

## 12-track Effects + Subscribe product E2E

Workflow run:

`38030777284`

Result: **PASS**

Exact E2E report:

```json
{"duration":7200.004,"effects":true,"encoder":"hevc_videotoolbox","fastPath":true,"mib":320.76484966278076,"sizeGate":"nonempty-only; Phase 2 has no release-size target","status":"PASS","subscribe":true,"tracks":12,"wallSeconds":15.39311125}
```

Verified:

- 12 MP3 audio tracks
- Effects enabled and exercised
- Subscribe enabled and exercised
- target duration about 2 hours (`7200.004 s`)
- 1920×1080
- 60 FPS
- HEVC via `hevc_videotoolbox`
- AAC stereo / 48 kHz validation in the QA gate
- fast product path active
- non-empty output
- render wall time `15.39311125 s`
- output size approximately `320.765 MiB`

Marker:

`TWELVE_TRACK_EFFECTS_SUBSCRIBE_E2E=PASS`

Phase 2 intentionally has no invented release-size floor or target.

## QA application artifact

Source QA artifact:

- artifact ID: `11661604955`
- artifact name: `ENDLUME-CANONICAL-GOOD-PRODUCT-QA`
- artifact archive digest: `sha256:20b280f648cf4b9725e324a9e0e3f7384cbb643702dc749f1d4ed702497ab1bc`
- application ZIP SHA-256: `0b374fffa3dbf057620d2f3a5b7919306df474767494ef2daead3bb319afb250`

The launch-only verification re-downloaded this exact artifact instead of rebuilding it.

## Isolated physical macOS launch

Launch-only workflow run:

`38031821392`

Job:

`114154187742`

Result: **PASS**

Verified:

- exact prior QA artifact downloaded successfully
- application ZIP SHA-256 matched
- app mounted automatically at `/Volumes/ENDLUME_CANONICAL_QA`
- app launched from `/Volumes/ENDLUME_CANONICAL_QA/ENDLUME-CANONICAL-GOOD-PRODUCT-QA.app`
- process was found after launch
- one GUI window was found
- window title: `ENDLUME YT Studio PEISOV`
- application icon converted/captured from the built bundle
- `/Applications/ENDLUME YT Studio PEISOV.app` did not exist before the test and still did not exist after the test
- mounted QA app was terminated and the volume detached after evidence capture

Markers:

- `ISOLATED_QA_LAUNCH=PASS`
- `OWNER_APPLICATIONS_APP_MODIFIED=NO`

Launch evidence artifact:

- artifact ID: `11662456121`
- name: `ENDLUME-CANONICAL-GOOD-PRODUCT-LAUNCH-EVIDENCE`
- artifact digest: `sha256:56637ddf741a4541ede64759ef2ba759f5616ec96db7b48cbfaa046bae01eb2b`

Evidence contains five files, including application icon, isolated-launch screenshot, PID/accessibility evidence, and status report.

## Licensed multi-screen UI gate

Status: **BLOCKED, not failed.**

Reason:

The clean hosted macOS runner has no valid ENDLUME GUI license/session. Product code correctly presents the activation gate. The existing `e2e-render` mechanism only authorizes render-start E2E behavior; it does not bypass the frontend activation screen.

No temporary frontend bypass was added. No raw production license key/session was committed, printed, copied into the workflow, or exposed in logs.

Therefore screenshots of the full licensed Project / Render / Effects / Subscribe / Settings surfaces are not claimed as physically accepted in this phase.

Marker:

`FULL_MULTI_SCREEN_QA=BLOCKED_NO_AUTHORIZED_QA_LICENSE`

## Owner/stable safety boundary

This Phase 2 work did not:

- replace or mutate the owner's installed `/Applications/ENDLUME YT Studio PEISOV.app`
- publish a stable release
- modify the live 10.0.12 updater package or manifest
- rotate updater signing keys
- merge Fast Engine work
- add a license bypass
- overwrite owner projects, library, settings, OAuth, or license data

## Current acceptance decision

The reconstructed product candidate `3f06c7329bd3821bc160e6d88c5b294fc0d82c2b` has passed all currently executable canonical product gates:

1. source reconstruction contract — PASS
2. TypeScript/Rust regression — PASS
3. production-like Apple Silicon build — PASS
4. 12-track Effects + Subscribe 2-hour product E2E — PASS
5. isolated physical macOS application launch — PASS
6. owner `/Applications` safety boundary — PASS
7. full licensed multi-screen GUI screenshot acceptance — BLOCKED pending an authorized QA license/session

**Do not label Phase 2 fully accepted until gate 7 is executed through an authorized license path.**
