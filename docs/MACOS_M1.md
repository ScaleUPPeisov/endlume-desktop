# ENDLUME macOS — Apple Silicon M1+

## Target
- Apple Silicon arm64, M1 priority.
- Minimum configured macOS: 11.0.
- Tauri 2 `.app` + `.dmg`.
- FFmpeg/FFprobe sidecars inside the application bundle.
- Fast Engine benchmarks `h264_videotoolbox` / `hevc_videotoolbox` and CPU fallback.

## Build alpha.8 on the M1
Use the root-level file:

`CHECK_AND_BUILD_ENDLUME_M1.command`

The script deliberately runs checks BEFORE producing a DMG:
1. Apple Command Line Tools.
2. Homebrew / Node.js / Rust.
3. FFmpeg + FFprobe + VideoToolbox detection.
4. `npm run build`.
5. `cargo check --target aarch64-apple-darwin`.
6. real FFmpeg smoke encode.
7. `tauri build --bundles app,dmg`.

Build logs: `build_logs/`.
Result: `src-tauri/target/aarch64-apple-darwin/release/bundle/`.

## First launch
ENDLUME asks for a license key. Rendering is local after activation.

## Commercial distribution later
An unsigned development DMG is suitable for our own testing. Selling/distributing to other Mac users requires Developer ID signing + Apple notarization. The updater will also require ENDLUME's separate updater signing key and release server.
