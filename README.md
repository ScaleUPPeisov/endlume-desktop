# ENDLUME Studio 1.0.0-alpha.8.2 — Tauri 2 / Rust

ENDLUME 1.0 is the clean rewrite of the proven 0.3.x workflow from PowerShell/WPF to Tauri 2 + Rust + FFmpeg.

## DESIGN LOCK
The UI/UX remains maximally close to the provided LoopForge reference. The Tauri rewrite is for stability, speed, macOS support and smooth UI — not for turning ENDLUME into a different dashboard product. See `DESIGN_LOCK.md`.

## Current alpha.8.2 core
- Windows 10/11 x64 target.
- macOS Apple Silicon M1+ target; M1 is the priority test machine.
- Recursive massive project discovery.
- Dynamic sequential render queue; jobs can be added while rendering.
- Crash/restart queue recovery.
- Image / Crossfade / Ping-pong / Original modes.
- 1080p / 2K / 4K, 24/30/60 FPS, H.264/H.265, bitrate cap 1–100 Mbps.
- Short master-loop + stream-copy long-video assembly.
- Deterministic music order, 1–10 sec crossfade, opt-in -14 LUFS, exact/whole-track modes.
- Persistent Effects / Subscribe library and cache.
- Effects/Subscribe live 6-second MP4 preview with direct drag/resize.
- Effects timeline; Subscribe first/second/repeat schedule.
- Ambient audio.
- FFprobe result verification + retry.
- Friendly UI errors; raw technical diagnostics are written to logs.
- Owner lifetime activation is implemented locally; commercial monthly license server is not configured yet.

## MacBook M1 — safest build path
1. Copy/unzip the project folder on your M1 Mac.
2. Double-click `INSTALL_ENDLUME_M1.command`.
3. The updater reuses previous npm/Cargo caches when available, prepares FFmpeg sidecars, and runs:
   - React/TypeScript production build;
   - Rust `cargo check` for `aarch64-apple-darwin`;
   - a real FFmpeg encode smoke test;
   - Tauri `.app` + `.dmg` build.
4. If any check fails, DMG is NOT produced and the builder leaves a log in `build_logs/`.

## Important commercial-release notes
- A DMG must be built on macOS.
- Public distribution to customers later requires Apple Developer signing/notarization.
- Production auto-updates require our signed updater artifacts + update endpoint.
- The current M1 builder uses the Mac's installed/Homebrew FFmpeg to prepare test sidecars. Before public sale we will replace this with vetted redistributable arm64 binaries so customers do not need Homebrew.

## Windows
Windows production installer is the next build target after the Tauri core compiles cleanly on M1. The same Rust/React codebase is used; Windows gets platform-specific FFmpeg sidecars and encoder benchmark.
