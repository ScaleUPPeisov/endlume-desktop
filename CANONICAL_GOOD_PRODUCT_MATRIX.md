# ENDLUME Canonical Good Product Matrix

This matrix describes the reconstructed October PRODUCT baseline before any Fast Engine transplant.

## PROJECT

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| Root/folder selection and drag-drop | 750 October product | `src/pages/ProjectPage.tsx` | PRESENT |
| Project scan / validation | 750 + late 8a0 recovery | `src/pages/ProjectPage.tsx`, `src-tauri/src/scan.rs` | PRESENT |
| Loop-mode controls | 750 | `src/pages/ProjectPage.tsx` | PRESENT |
| Render settings and output selection | 750 | `src/pages/ProjectPage.tsx` | PRESENT |
| Per-project effect selection | late 8a0 | `src/pages/ProjectPage.tsx`, `src/store.ts` | PRESENT |
| Missing/stale asset recovery | late 8a0 | `src/pages/ProjectPage.tsx`, `src/components/recovery.tsx`, `src-tauri/src/assets.rs` | PRESENT |

## EFFECTS

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| Visible Effects ON/OFF | 750 modern UI, retained by 8a0 | `src/pages/ProjectPage.tsx` | PRESENT |
| Effects editor | 750 | `src/pages/Editors.tsx` | PRESENT |
| Effect selection | 750 + 8a0 persisted selection | `src/pages/Editors.tsx`, `src/pages/ProjectPage.tsx`, `src/store.ts` | PRESENT |
| OFF / ALWAYS / INTERVAL | 750 | `src/pages/Editors.tsx`, `src/types.ts` | PRESENT |
| Chroma key parameters | 750 | `src/pages/Editors.tsx` | PRESENT |
| Luma parameters | 750 | `src/pages/Editors.tsx` | PRESENT |
| Screen mode | 750 | `src/pages/Editors.tsx` | PRESENT |
| Similarity / blend | 750 | `src/pages/Editors.tsx` | PRESENT |
| Position / scale | 750 | `src/pages/Editors.tsx` | PRESENT |
| Timing | 750 | `src/pages/Editors.tsx` | PRESENT |
| Live preview | 750 | `src/pages/Editors.tsx`, `src/components/LiveCompositePreview.tsx`, `src-tauri/src/live_preview.rs` | PRESENT |
| Project/library persistence | 750 + late 8a0 | `src/pages/ProjectPage.tsx`, `src-tauri/src/persistence.rs` | PRESENT |
| Repair-required state | late 8a0 | `src/pages/ProjectPage.tsx`, `src/types.ts` | PRESENT |

## SUBSCRIBE

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| Visible Subscribe ON/OFF | 750 modern UI | `src/pages/ProjectPage.tsx` | PRESENT |
| SubscribeEditor | 750 | `src/pages/Editors.tsx` | PRESENT |
| Source asset | 750 + 8a0 repair | `src/pages/Editors.tsx`, `src/pages/ProjectPage.tsx` | PRESENT |
| Position / scale | 750 | `src/pages/Editors.tsx` | PRESENT |
| Duration | 750 | `src/pages/Editors.tsx` | PRESENT |
| First appearance | 750 | `src/pages/Editors.tsx` | PRESENT |
| Interval / repeat | 750 | `src/pages/Editors.tsx` | PRESENT |
| Preview | 750 | `src/pages/Editors.tsx`, `src/components/LiveCompositePreview.tsx` | PRESENT |
| Persistence | 750 + 8a0 | `src-tauri/src/persistence.rs`, `src/pages/ProjectPage.tsx` | PRESENT |
| Missing-asset refusal/repair | late 8a0 | `src/pages/ProjectPage.tsx`, `src-tauri/src/assets.rs` | PRESENT |

## BACKGROUND MUSIC

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| Background Music enable/disable | 750 October product | `src/pages/ProjectPage.tsx` | PRESENT |
| Source selection and persisted library state | 750 | `src/pages/ProjectPage.tsx`, `src/store.ts`, `src-tauri/src/persistence.rs` | PRESENT |
| Volume | 750 | `src/pages/ProjectPage.tsx` | PRESENT |
| EQ controls | 750 | `src/pages/ProjectPage.tsx`, `src/types.ts` | PRESENT |
| Loop behavior | 750 | `src/pages/ProjectPage.tsx`, backend render product baseline | PRESENT |

## PREVIEW

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| Live composite preview UI | 750 | `src/components/LiveCompositePreview.tsx` | PRESENT |
| Effects/Subscribe preview controls | 750 | `src/pages/Editors.tsx` | PRESENT |
| Preview backend | 750 | `src-tauri/src/live_preview.rs`, `src-tauri/src/preview.rs` | PRESENT |
| Asset/recovery-aware preview inputs | late 8a0 + 750 | `src-tauri/src/assets.rs`, `src/pages/ProjectPage.tsx` | PRESENT |

## RENDER

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| Modern Render Center | published/current October | `src/pages/RenderPage.tsx` | PRESENT |
| Queue | current October + late 8a0 backend recovery | `src/pages/RenderPage.tsx`, `src-tauri/src/queue.rs` | PRESENT |
| Progress / stages | current October | `src/pages/RenderPage.tsx` | PRESENT |
| ETA / calculating state | current October | `src/pages/RenderPage.tsx` | PRESENT |
| Elapsed / remaining | current October | `src/pages/RenderPage.tsx` | PRESENT |
| Resource telemetry | current October | `src/pages/RenderPage.tsx` | PRESENT |
| Cancel | current October | `src/pages/RenderPage.tsx`, queue IPC | PRESENT |
| Open output | current October | `src/pages/RenderPage.tsx` | PRESENT |
| Return to project | current October | `src/pages/RenderPage.tsx` | PRESENT |
| Late render orchestration fix | 8a0 | `src-tauri/src/render.rs` | PRESENT |

## LIBRARY

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| Library screen | published/current October | `src/pages/LibraryPage.tsx` | PRESENT |
| Late recovery-state handling | 8a0 | `src/pages/LibraryPage.tsx`, `src/components/recovery.tsx` | PRESENT |
| Effects/Subscribe/Ambient persisted library | 750 + 8a0 persistence | `src/store.ts`, `src-tauri/src/persistence.rs` | PRESENT |

## SETTINGS

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| GENERAL | published/current October | `src/pages/SettingsPage.tsx` | PRESENT |
| FAST ENGINE section | published/current October | `src/pages/SettingsPage.tsx` | PRESENT |
| UPDATES | published/current October | `src/pages/SettingsPage.tsx` | PRESENT |
| ABOUT | published/current October | `src/pages/SettingsPage.tsx` | PRESENT |
| Current branding | published/current October | `src/pages/SettingsPage.tsx`, `src/platform-brand.ts` | PRESENT |

## UPDATER UI

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| Update controls/status UI | published/current October | `src/pages/SettingsPage.tsx`, `src/tauri.ts` | PRESENT |
| October release history | published/current October | `src/components/ReleaseHistory.tsx` | PRESENT |
| Alpha-only history as primary history | forbidden broken lineage | n/a | PRESENT AS ABSENT (required) |

## LICENSE

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| License UI/runtime integration | published/current October | `src/pages/App.tsx`, `src/tauri.ts`, backend license modules | PRESENT |
| License state retained by reconstruction | published/current October | persistence/backend | PRESENT |
| Owner license reset | forbidden action | n/a | PRESENT AS NOT PERFORMED |

## STATE / PERSISTENCE

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| Project/store state | 750 + 8a0 | `src/store.ts` | PRESENT |
| Library persistence | 750 + 8a0 | `src-tauri/src/persistence.rs` | PRESENT |
| Queue recovery | late 8a0 | `src-tauri/src/queue.rs` | PRESENT |
| Model migration/recovery fields | late 8a0 | `src-tauri/src/model.rs`, `src/types.ts` | PRESENT |
| Scan recovery state | late 8a0 | `src-tauri/src/scan.rs` | PRESENT |

## APP BRANDING

| Feature | Source lineage | Source file | Final status |
|---|---|---|---|
| ENDLUME current product visual layer | af | `src/cinematic-ui-polish.css`, `src/loopforge-reference.css`, `src/main.tsx` | PRESENT |
| Modern app icon | published stable / 750 | `src-tauri/icons/**` | PRESENT |
| Required `icon.icns` blob `1475287a7780c467e5e7a9dbca5d4a2fc4633e0f` | published stable / 750 | `src-tauri/icons/icon.icns` | PRESENT |
| Old infinity icon blob `d550b4e67431911140fd6f3c0f3eac3488eb4fce` | forbidden broken lineage | n/a | PRESENT AS ABSENT (required) |
| October ReleaseHistory | published stable/current October | `src/components/ReleaseHistory.tsx` | PRESENT |

## Phase boundary

Fast Engine source `a7a399e83de8b9248e2065c6dda1f9079ded6565` has **NOT** been transplanted in this phase. The current matrix is a PRODUCT baseline only; runtime/build/physical isolated QA still gates designation of the final `CANONICAL_GOOD_PRODUCT_HEAD`.
