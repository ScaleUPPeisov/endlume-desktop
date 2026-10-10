# ENDLUME 10.0.13 — Phase 3 Fast Engine Transplant Map

## Frozen sources

- PRODUCT BASE: `3f06c7329bd3821bc160e6d88c5b294fc0d82c2b`
- FAST ENGINE SOURCE: `a7a399e83de8b9248e2065c6dda1f9079ded6565`
- MERGE BASE: `ee52a1690a8fa8aa1ee2b0337baed2531a5ceca0`
- Rule: semantic transplant only. No whole-branch merge/rebase. Canonical product contracts win outside the proven Fast Engine architecture.

## Engine delta inventory

| Source file | Source functions / responsibility | Destination | Action | Why |
|---|---|---|---|---|
| `src-tauri/src/fast_render.rs` | clean fast eligibility; static/periodic/Subscribe HEVC path; MP3 packet-copy; manifest sample selection; fast verification | same | **PORT** | Core accepted Fast Engine architecture. Port backend semantics while adapting eligibility, Subscribe scheduling, anchors and success result to the canonical product contract. |
| `src-tauri/src/visual_spec.rs` | periodic eligibility; frame/period math; shared FFmpeg visual filter construction | same | **PORT + SEMANTIC ADAPT** | Backend-only dependency of Fast Engine; absent from canonical product. Preserve periodic architecture, but canonical Phase 2 compositor semantics win for image crop, opacity, chromakey/despill, target geometry and round-EQ handling. |
| `src-tauri/src/mp4_manifest.rs` | MP4 sample-table expansion/remap | same | **ALREADY_PRESENT** | Canonical and Fast Engine refs resolve to identical blob `aa018754811c67d10cea59cde437145d025c5304`; do not overwrite. |
| `src-tauri/src/queue.rs` | dispatch `try_render_job` before legacy fallback | canonical `queue.rs` | **MERGE** | Preserve canonical persistence, terminal snapshots, license hold, selected-effect identity, recovery, errors and Render Center contract. Add only semantic fast-dispatch integration. |
| `src-tauri/src/render.rs` | historical Subscribe CFR boundary fixes / static Subscribe encoder safety | canonical `render.rs` | **ALREADY_PRESENT / REVIEW ONLY** | Canonical renderer is substantially newer and already contains explicit fixed-frame Subscribe composition, CFR/timescale handling and zero-copy manifest paths. Never replace whole file; port only a demonstrably missing invariant. |
| `src-tauri/src/preview.rs` | old Fast branch preview alignment | canonical `preview.rs` | **REJECT** | Phase 2 canonical Preview wins. Fast Engine must not redefine Preview. Parity is a test gate, not a reason to import old preview code. |
| `src-tauri/src/lib.rs` | module registration for Fast Engine | canonical `lib.rs` | **MERGE** | Add only backend module declarations and one dispatcher that returns the canonical `RenderOutcome`. Preserve live preview, assets, updater, VYRON bridge, E2E harness and all current commands/setup. |
| `src-tauri/Cargo.toml` | historical acceptance feature/default-run additions | canonical Cargo manifest | **NOT NEEDED** | Canonical already has its own `e2e-render` feature and modern dependency surface. Do not replace package metadata/version/features. |
| `src-tauri/src/acceptance.rs` | historical Fast branch acceptance harness | canonical QA | **REJECT / NOT NEEDED** | Canonical product already has a newer E2E render harness. Phase 3 tests exercise the current product contract rather than reintroducing the old harness. |
| Fast-branch frontend / CSS / icon / ReleaseHistory / product state | historical product/release surface | none | **REJECT** | Frozen product surface. No old frontend, icon, changelog, alpha state or release plumbing. |

## Semantic conflict rules

### Canonical product wins

- selected Effects identity and one-effect-per-project contract
- Subscribe/product state and persistence
- current `usageMode`, `intervalSec`, `firstAppearance`, `customFirstAtSec`, `showDurationSec`
- current target/anchor placement and opacity
- current chromakey/despill and round equalizer compositor semantics
- Background Music and EQ behavior
- queue persistence, cancel, recovery, terminal payloads and license hold
- current Preview / Live Preview behavior
- current Render Center and UI command contracts
- updater/VYRON bridge/current project model

### Fast Engine wins only when eligible

- Apple Silicon clean fast eligibility
- one-still static HEVC path
- proven periodic visual cycle reuse
- deterministic Subscribe sample selection
- MP4 manifest expansion/remap
- clean MP3 packet preservation / stream-copy
- safe fallback to canonical renderer when eligibility or execution is not proven

## Implemented semantic bridge

- `fast_render.rs`: accepted Fast Engine architecture retained; success boundary adapted to canonical `render::RenderOutcome`.
- `fast_render.rs`: current Phase 2 Subscribe interval/first-appearance/show-duration semantics are used; legacy scheduling remains supported only as a compatibility case.
- `fast_render.rs`: current product anchors are resolved before fast composition.
- `fast_render.rs`: normalize, crossfade, Background Music/EQ, unsupported interval/timed effects and unsafe combinations reject to canonical render.
- `fast_render.rs`: product license hold is checked between fast stages; license cancellation is propagated, not converted to fallback.
- `visual_spec.rs`: accepted period/common-cycle architecture retained and adapted to canonical cover/crop, opacity, geometry, chromakey/despill and round equalizer processing.
- `lib.rs`: only `fast_render` / `visual_spec` module declarations plus `render_with_phase3_fast` dispatcher added.
- `queue.rs`: existing worker contract retained; its single render dispatch now calls `render_with_phase3_fast`.
- E2E render harness uses the same dispatcher, so acceptance measures the actual Phase 3 path rather than bypassing it.
- canonical `render.rs`: unchanged.
- canonical `preview.rs`: unchanged.
- `mp4_manifest.rs`: unchanged and identical to accepted Fast Engine blob.

## Phase 3 acceptance architecture

- Hosted gate: frozen UI diff, TypeScript, frontend build, Rust tests/check, isolated ARM64 candidate build.
- Physical gate: exact hosted candidate is downloaded to the owner M-series runner and extracted under `$RUNNER_TEMP`; it is never copied into `/Applications`.
- Owner app binary must equal `2df386c00da09e76f90218061e7f57ccfba2249a654ec1262b06000b322eb9d7` before and after acceptance.
- Owner app must not be running during the physical gate.
- Owner app-data and managed-session keychain fingerprints are captured before/after and must remain identical.
- Candidate E2E processes run with isolated `HOME`; no owner state, OAuth or Google/YouTube session reset is permitted.
- Primary corpus matches the accepted performance profile: one 1920×1080 still + twelve 900-second 320 kbps MP3 tracks = ~3 hours.
- Static, periodic and Subscribe 3h cases require Phase 3 Fast Engine, HEVC, 60 FPS, MP3 packet preservation, full decode, seek and DTS validity, 400–600 MB and ≤10 s.
- Periodic case additionally checks visibility, motion, long-run phase, seam and canonical Preview parity.
- Subscribe case additionally checks current Phase 2 first appearance, duration/disappearance, repeat timing, position/scale, animation and canonical Preview parity.
- Combined product case uses Effects ON + Subscribe ON for 2h+ and compares against the Phase 2 `15.393 s` reference.
- Fallback cases cover Normalize, Crossfade and an unsupported interval effect and require canonical-render output.
- No Phase 3 workflow contains release, stable mutation, updater publication or owner-app installation steps.

## Final gate rule

One exact `PHASE_3_FAST_ENGINE_HEAD` only. Hosted and physical evidence must both correspond to that SHA. If any physical or regression gate fails, Phase 3 is `BLOCKED`; there is no release.
