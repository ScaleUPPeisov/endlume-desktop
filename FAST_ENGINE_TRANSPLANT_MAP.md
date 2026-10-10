# ENDLUME 10.0.13 — Phase 3 Fast Engine Transplant Map

## Frozen sources

- PRODUCT BASE: `3f06c7329bd3821bc160e6d88c5b294fc0d82c2b`
- FAST ENGINE SOURCE: `a7a399e83de8b9248e2065c6dda1f9079ded6565`
- MERGE BASE: `ee52a1690a8fa8aa1ee2b0337baed2531a5ceca0`
- Rule: semantic transplant only. No whole-branch merge/rebase. Canonical product contracts win outside the proven Fast Engine architecture.

## Engine delta inventory

| Source file | Source functions / responsibility | Destination | Action | Why |
|---|---|---|---|---|
| `src-tauri/src/fast_render.rs` | clean fast eligibility; static/periodic/Subscribe HEVC path; MP3 packet-copy; manifest sample selection; fast verification | same | **PORT** | Core accepted Fast Engine. Port backend semantics while adapting success result to the canonical product render/queue contract. |
| `src-tauri/src/visual_spec.rs` | periodic eligibility; frame/period math; shared FFmpeg visual filter construction | same | **PORT** | Backend-only dependency of Fast Engine; absent from canonical product. No UI state. |
| `src-tauri/src/mp4_manifest.rs` | MP4 sample-table expansion/remap | same | **ALREADY_PRESENT** | Canonical and Fast Engine refs resolve to identical blob `aa018754811c67d10cea59cde437145d025c5304`; do not overwrite. |
| `src-tauri/src/queue.rs` | dispatch `try_render_job` before legacy fallback | canonical `queue.rs` | **MERGE** | Preserve canonical persistence, terminal snapshots, license hold, selected-effect identity, recovery, errors and Render Center contract. Add only semantic fast-dispatch integration. |
| `src-tauri/src/render.rs` | historical Subscribe CFR boundary fixes / static Subscribe encoder safety | canonical `render.rs` | **ALREADY_PRESENT / REVIEW ONLY** | Canonical renderer is substantially newer and already contains explicit fixed-frame Subscribe composition, CFR/timescale handling and zero-copy manifest paths. Never replace whole file; port only a demonstrably missing invariant. |
| `src-tauri/src/preview.rs` | old Fast branch preview alignment | canonical `preview.rs` | **REJECT** | Phase 2 canonical Preview wins. Fast Engine must not redefine Preview. Parity is a test gate, not a reason to import old preview code. |
| `src-tauri/src/lib.rs` | module registration for Fast Engine | canonical `lib.rs` | **MERGE** | Add only backend module declarations and one dispatcher that returns the canonical `RenderOutcome`. Preserve live preview, assets, updater, VYRON bridge, E2E harness and all current commands/setup. |
| `src-tauri/Cargo.toml` | historical acceptance feature/default-run additions | canonical Cargo manifest | **NOT NEEDED unless compile proves otherwise** | Canonical already has its own `e2e-render` feature and modern dependency surface. Do not replace package metadata/version/features. |
| `src-tauri/src/acceptance.rs` | historical Fast branch acceptance harness | canonical QA | **REJECT / NOT NEEDED** | Canonical product already has a newer E2E render harness. Phase 3 tests should exercise the current product contract, not reintroduce the old harness. |
| Fast-branch frontend / CSS / icon / ReleaseHistory / workflows unrelated to isolated Phase 3 evidence | historical product/release surface | none | **REJECT** | Frozen product surface. No old frontend, icon, changelog, alpha state or release plumbing. |

## Semantic conflict rules

### Canonical product wins

- selected Effects identity and one-effect-per-project contract
- Subscribe/product state and persistence
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

## Initial implementation gate

1. Add `visual_spec.rs` backend helper.
2. Add `fast_render.rs` backend engine, adapting only the success/result boundary required by canonical `RenderOutcome` / queue semantics.
3. Add `mod fast_render; mod visual_spec;` to canonical `lib.rs`; no other lib surface changes unless compile proves required.
4. Integrate queue function-by-function; never replace canonical `queue.rs`.
5. Keep canonical `render.rs` and `preview.rs` frozen unless a concrete acceptance failure proves a missing invariant.
6. Run UI frozen-diff gate before candidate acceptance.
7. No release, updater mutation, stable mutation or owner-app replacement in Phase 3.

## Implemented semantic bridge

- `visual_spec.rs`: exact accepted backend blob transplanted.
- `fast_render.rs`: accepted architecture retained; success boundary adapted to canonical `render::RenderOutcome`.
- `fast_render.rs`: product license hold is checked between fast stages; license cancellation is propagated, not converted to legacy fallback.
- `lib.rs`: only `fast_render` / `visual_spec` module declarations plus `render_with_phase3_fast` dispatcher added.
- `queue.rs`: existing worker contract retained; its single render dispatch now calls `render_with_phase3_fast`.
- E2E render harness uses the same dispatcher, so acceptance measures the actual Phase 3 path rather than bypassing it.
- canonical `render.rs`: unchanged.
- canonical `preview.rs`: unchanged.
- `mp4_manifest.rs`: unchanged and identical to accepted Fast Engine blob.
- Phase 3 compile/ARM64 candidate workflow added; it explicitly blocks updater/release actions and applies a frozen-UI diff gate.
