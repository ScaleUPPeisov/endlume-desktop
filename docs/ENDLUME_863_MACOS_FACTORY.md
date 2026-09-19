# ENDLUME YT Studio PEISOV 8.63 — macOS + Content Factory

Source baseline: ENDLUME 8.62 production source from commit `8d36f0c3a15396d19236d797a3b658679c135562`.

Working branch: `feature/endlume-863-macos-factory`

Backup: `backup/endlume-862-before-863-macos-factory-20260919`

## Product priority

Primary target now is macOS Apple Silicon M1+ because the owner works daily on Mac. Windows 8.62 production remains immutable.

Do not rewrite ENDLUME. Extend the current Tauri 2 + React 19 + Rust + FFmpeg architecture.

## Already present in current source

- Project root scanning and nested project discovery.
- Image/video loop modes: image, crossfade, ping-pong, original.
- 1080p/2K/4K controls, 24/30/60 FPS, H.264/H.265, presets.
- Duration presets 1 / 1.5 / 2 / 3 / 4 / 8 / 10 / 12 h.
- Bitrate slider 1–100 Mbps.
- Exact-duration vs whole-track mode.
- Crossfade 0–10 sec and optional LUFS normalization.
- Auto encoder benchmark (VideoToolbox on macOS, NVENC/QSV/AMF on Windows).
- Managed Effects / Subscribe / ambient library and cache.
- Queue persistence / crash recovery.
- Render Center progress, elapsed time, ETA and queue estimation.
- FFprobe output validation and strict render contracts.
- 8.62 queue dedupe, revoke-finalization hardening and natural output size.

## 8.63 critical macOS gaps

1. macOS must use the same managed license backend as Windows instead of the legacy local-owner-only path.
2. Session token must use native macOS Keychain through the existing `keyring apple-native` dependency.
3. New managed/customer keys must work on both Windows and macOS; OWNER remains lifetime.
4. Heartbeat / remote pause / revoke / device binding / render telemetry must work on macOS.
5. macOS updater must stop depending on GitHub CLI. Use the existing signed Tauri updater flow with mandatory SHA-256 verification.
6. Brand macOS as `ENDLUME YT Studio PEISOV`, including bundle title and canonical /Applications app name.
7. Bundle FFmpeg/ffprobe for Apple Silicon so the user installs a normal application without extra dependencies.
8. Preserve VideoToolbox and 8.62 render quality/performance contracts.

## Factory work after macOS parity

- Keep high-volume root-folder workflow; no per-channel profile requirement.
- Improve multi-image sequencing and short-video seamless looping.
- Timeline for Effects / Subscribe with drag, resize and time ranges.
- Persistent named effect/subscribe presets with animated preview.
- Resume queues after crash/reboot without re-rendering completed projects.
- Result verification + controlled retry for corrupt output.
- Render Center CPU/RAM/disk/per-stage timing and whole-queue finish time.
- Batch output naming from source folder and separate timecodes folder + track list + project log.
- Keep UI compositor-friendly and target stable 60 FPS, with 120 Hz responsiveness where the platform/webview allows it.
- YouTube upload/competitor analysis remains out of scope for this phase.

## Release rule

Do not modify existing Windows 8.62 release/tag/assets. 8.63 is a new candidate. macOS release requires real Apple Silicon build/regression and bundled sidecar verification. Automatic updater publication remains fail-closed until the matching signing key is available.
