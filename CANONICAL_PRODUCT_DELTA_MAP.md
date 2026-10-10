# ENDLUME Canonical Product Delta Map

Phase 2 source reconstruction only. No Fast Engine transplant, release, stable mutation, updater publish, or owner-app install is authorized by this document.

## Anchors

- Published production safety anchor: `1954afb0632f05316aa7be493599a2c90d25dfe3`
- Common October product: `750623fde68ef73a58429a5fdef1b85d541c7e12`
- Modern October UI source: `af7883d1185a4349f003ffc1c3c0c8ef98fca4e7`
- Late October product/macOS source: `8a0b29b0468b5e665705e20c6a8635ca4c73ba90`
- Reconstruction product commit before audit/QA-only commits: `3f06c7329bd3821bc160e6d88c5b294fc0d82c2b`
- Forbidden product sources in this phase: broken `0445923773dc276580fcdaf719d69a3e6bbddef5`, Fast Engine `a7a399e83de8b9248e2065c6dda1f9079ded6565`

## Ancestry and merge policy

`1954afb -> 750623f` is a linear product evolution. From `750623f`, the two legitimate October lines diverge:

- UI line: `750623f -> d0ad115 -> ... -> d8fce4b -> af7883d`
- late product/macOS line: `750623f -> d76e45f -> 804468e -> 016571c -> 4f1b0f2 -> 8a0b29b`

The final endpoint delta `750623f -> af7883d` contains only `src/main.tsx` plus the two visual CSS layers. The final endpoint delta `750623f -> 8a0b29b` contains 15 non-CI product/build files. These endpoint deltas do not overlap, so the canonical reconstruction uses exact source blobs rather than guessed conflict resolutions.

## Product file map

| PATH | 1954 STATE | 750 STATE | AF STATE | 8A0 STATE | FINAL SOURCE CHOICE | WHY |
|---|---|---|---|---|---|---|
| `src/pages/App.tsx` | published stable | updated by common October product | same as 750 | late product delta | **8a0** | endpoint `750->8a0` contains a legitimate App recovery/product change |
| `src/pages/Editors.tsx` | published stable | modern Effects/Subscribe editor | same as 750 | same final endpoint state as 750 | **750** | modern editor already present; no endpoint 8a0 delta |
| `src/pages/LibraryPage.tsx` | published stable | October product | same as 750 | late product delta | **8a0** | preserves later recovery/state behavior |
| `src/pages/ProjectPage.tsx` | published stable | modern October Project UI | same as 750 | late Effects/asset-recovery delta | **8a0** | required later stale/asset recovery plus persisted effect selection |
| `src/pages/RenderPage.tsx` | published modern Render Center | modern Render Center | same as 750 | same final endpoint state as 750 | **750** | keeps queue/progress/stages/ETA/elapsed/remaining/resources/cancel/open-output UI |
| `src/pages/SettingsPage.tsx` | current October Settings | current October Settings | same as 750 | same final endpoint state as 750 | **750** | avoids stale alpha-era Settings; retains General/Fast Engine/Updates/About |
| `src/components/LiveCompositePreview.tsx` | present | updated common October preview | same as 750 | same final endpoint state as 750 | **750** | current preview UI already present |
| `src/components/ReleaseHistory.tsx` | October 10.0.x history | same/current | same/current | same/current | **750** | canonical October release history; do not use embedded alpha-only history |
| `src/components/recovery.tsx` | published stable | common October state | same as 750 | late product delta | **8a0** | later recovery surface must not disappear |
| `src/components/ui.tsx` | published UI primitives | current October primitives | same as 750 | same final endpoint state as 750 | **750** | no later legitimate endpoint change |
| `src/store.ts` | published persistence/store | common October store | same as 750 | late product delta | **8a0** | later persisted selection/recovery state |
| `src/types.ts` | published contracts | common October contracts | same as 750 | late product delta | **8a0** | required late state/asset contract fields |
| `src/tauri.ts` | published IPC bridge | common October bridge | same as 750 | same final endpoint state as 750 | **750** | no late endpoint change |
| `src/main.tsx` | published bootstrap | common October bootstrap | loads cinematic + LoopForge layers | same as 750 | **af** | exact modern visual-layer entrypoint |
| `src/cinematic-ui-polish.css` | absent | absent | added | absent from 8a0 divergence | **af** | modern cinematic visual layer |
| `src/loopforge-reference.css` | absent | absent | added | absent from 8a0 divergence | **af** | frame-matched modern reference layer |
| `src-tauri/src/assets.rs` | published asset logic | common October | same as 750 | late delta | **8a0** | later asset recovery/lookup behavior |
| `src-tauri/src/cache.rs` | published cache | common October | same as 750 | late delta | **8a0** | later cache correctness fix |
| `src-tauri/src/lib.rs` | published backend | updated common October | same as 750 | same final endpoint state as 750 | **750** | no 8a0 endpoint delta; Fast Engine lib not allowed |
| `src-tauri/src/live_preview.rs` | published preview backend | updated common October | same as 750 | same final endpoint state as 750 | **750** | final 8a0 endpoint does not differ from 750 |
| `src-tauri/src/model.rs` | published model | common October | same as 750 | late delta | **8a0** | later recovery/persistence model fields |
| `src-tauri/src/mp4_manifest.rs` | published October implementation | current October implementation | same as 750 | same final endpoint state as 750 | **750** | explicitly preserve product baseline; Fast Engine version forbidden in Phase 2 |
| `src-tauri/src/persistence.rs` | published persistence | common October | same as 750 | late delta | **8a0** | substantial later persistence/migration handling |
| `src-tauri/src/preview.rs` | published preview | updated common October | same as 750 | same final endpoint state as 750 | **750** | no late endpoint delta |
| `src-tauri/src/queue.rs` | published queue | updated common October | same as 750 | late delta | **8a0** | later queue recovery behavior |
| `src-tauri/src/render.rs` | published render orchestration | common October | same as 750 | late delta | **8a0** | later product/macOS behavior; not Fast Engine `fast_render.rs` |
| `src-tauri/src/scan.rs` | published scan | updated common October | same as 750 | late delta | **8a0** | later scan/recovery fix |
| `src-tauri/src/system.rs` | published system layer | updated common October | same as 750 | same final endpoint state as 750 | **750** | no late endpoint delta |
| `scripts/sign-macos-ffmpeg-runtime.mjs` | absent | absent | absent | added | **8a0** | legitimate late macOS runtime signing support |
| `scripts/tauri-cli.mjs` | published/common script | common October | same as 750 | late delta | **8a0** | required late macOS build/runtime behavior |
| `scripts/prepare-macos-ffmpeg-runtime.mjs` | published/common | current at 750 | same as 750 | same final endpoint state as 750 | **750** | no final endpoint delta |
| `scripts/verify-macos-ffmpeg-bundle.mjs` | published/common | current at 750 | same as 750 | same final endpoint state as 750 | **750** | no final endpoint delta |
| `src-tauri/icons/icon.icns` | modern icon | modern icon | modern icon | modern icon | **750 exact modern family** | required blob `1475287a7780c467e5e7a9dbca5d4a2fc4633e0f` |
| `src-tauri/icons/32x32.png` | modern family | modern family | modern family | modern family | **750 exact modern family** | prevent old infinity regression |
| `src-tauri/icons/128x128.png` | modern family | modern family | modern family | modern family | **750 exact modern family** | prevent old infinity regression |
| `src-tauri/icons/128x128@2x.png` | modern family | modern family | modern family | modern family | **750 exact modern family** | prevent old infinity regression |
| `src-tauri/icons/icon.png` | modern family | modern family | modern family | modern family | **750 exact modern family** | prevent old infinity regression |
| `src-tauri/icons/icon.ico` | published family | same family | same family | same family | **750** | unchanged cross-platform identity |
| `assets/**` | published product assets | inherited unless explicitly changed in linear 1954->750 history | same as 750 | same unless endpoint diff says otherwise | **750** | no divergent endpoint override required |
| `public/**` | published product public assets | inherited unless explicitly changed in linear 1954->750 history | same as 750 | same unless endpoint diff says otherwise | **750** | no divergent endpoint override required |
| all other CSS inherited from 750 | published/current | current October | inherited | inherited | **750** | only two visual CSS files are intentionally overlaid from af |

## Exact late 8a0 endpoint integration

The exact `750623f -> 8a0b29b` endpoint diff contains **15** non-CI paths. All 15 are represented in the reconstruction:

1. `scripts/sign-macos-ffmpeg-runtime.mjs` — PORTED
2. `scripts/tauri-cli.mjs` — PORTED
3. `src-tauri/src/assets.rs` — PORTED
4. `src-tauri/src/cache.rs` — PORTED
5. `src-tauri/src/model.rs` — PORTED
6. `src-tauri/src/persistence.rs` — PORTED
7. `src-tauri/src/queue.rs` — PORTED
8. `src-tauri/src/render.rs` — PORTED
9. `src-tauri/src/scan.rs` — PORTED
10. `src/components/recovery.tsx` — PORTED
11. `src/pages/App.tsx` — PORTED
12. `src/pages/LibraryPage.tsx` — PORTED
13. `src/pages/ProjectPage.tsx` — PORTED
14. `src/store.ts` — PORTED
15. `src/types.ts` — PORTED

Files touched during the 8a0 commit lineage but byte-identical again at the final endpoint (for example `Editors.tsx`, `live_preview.rs`, and supporting FFmpeg QA/preparation scripts) are **ALREADY PRESENT** in the 750 foundation and are not counted as endpoint fixes.

### 8A0_PRODUCT_FIXES_TOTAL

- TOTAL: **15**
- PORTED: **15**
- ALREADY_PRESENT: **endpoint-identical support files retained from 750; not counted in TOTAL**
- SUPERSEDED: **0**
- REJECTED: **0**
- MISSING: **NONE**

## Visual overlay integration

Exact `af7883d` product overlay:

- `src/cinematic-ui-polish.css` blob `65033dcb913767944340a178f5cae0c71d5f8ae8`
- `src/loopforge-reference.css` blob `0703486098241dc1b1a58d93fadcc50577dd0cd7`
- `src/main.tsx` blob `810e98fdff470388a6584ff9fa9f7a4ea442af0c`

All three are present in the reconstruction.

## Icon gate

Modern icon family retained from the published/common October product.

- Required `src-tauri/icons/icon.icns`: `1475287a7780c467e5e7a9dbca5d4a2fc4633e0f`
- Forbidden old-infinity `icon.icns`: `d550b4e67431911140fd6f3c0f3eac3488eb4fce`

The forbidden blob is not selected anywhere in the canonical reconstruction tree.

## Fast Engine boundary

No files were sourced from `a7a399e83de8b9248e2065c6dda1f9079ded6565` or `0445923773dc276580fcdaf719d69a3e6bbddef5` in this reconstruction. In particular, no Phase-3 Fast Engine `fast_render.rs` or `mp4_manifest.rs` transplant has occurred.
