# ENDLUME Studio 1.0 — Product Specification

## Product goal
ENDLUME is a high-speed desktop content factory for long YouTube videos. Priority order: (1) speed, (2) preserve source visual/audio quality, (3) stable unattended queues, (4) polished high-refresh UI.

## Target platforms
- Windows 10/11 x64.
- macOS Apple Silicon, priority M1; modern macOS, minimum configured as macOS 12 for alpha.
- Platform-specific render optimization is allowed; project/preset binary compatibility is not a priority if it hurts speed.

## Daily workflow
- Root folder may contain channels, subfolders and hundreds of individual projects.
- Each project requires at least one visual (image or short AI video) and at least one audio track.
- Missing visual => reject project immediately and show folder name + “нет изображения/видео”.
- Missing audio => reject project immediately and show folder name + “нет песен”.
- One project can use multiple numbered images in order.
- Short AI video (e.g. 5 sec) must become a seamless long loop using Crossfade/Ping-pong/other loop mode.
- Typical audio: 10–15 songs.

## Render controls
- Modes: Image / Crossfade / Ping-pong / No processing.
- Duration presets: 1h / 1.5h / 2h / 3h / 4h / 8h / 10h / 12h.
- Bitrate UI: 1–100 Mbps; VBR/capped quality mode internally where appropriate.
- 1080p / 2K / 4K; 24/30/60 FPS; H.264/H.265.
- Audio normalization -14 LUFS is opt-in per project.
- Track crossfade slider 1–10 sec.
- Preserve audio as closely as possible; avoid repeated lossy transcodes.
- Duration modes: exact target or whole-track finish. Whole-track mode may extend modestly beyond target; prefer +1–4 min rather than cutting a song in half.

## Massive queue
- Recursively discover hundreds of projects from one root folder.
- Render sequentially by default for stability and disk throughput.
- A failed project is marked error and queue continues automatically.
- Drag-reorder jobs.
- Show 1/500, 2/500 etc., total ETA and expected finish clock time.
- On OS/power interruption: persist queue, mark in-flight job interrupted, warn user to inspect it, then continue from next unfinished project.
- Verify every output with FFprobe before DONE. Corrupt/invalid output => automatic retry with bounded attempts.

## Render Center
For each job show name, duration, resolution, FPS, tracks, start, elapsed, remaining, size, CPU, RAM, GPU and VRAM where available. Smooth animated progress with decimals. Detailed stages include input validation, benchmark/encoder choice, master-loop, effects cache, subscribe cache, audio analysis, audio cache, long-video stream-copy assembly, metadata/timecodes, FFprobe verification and done.

## Effects
- Unlimited practical library.
- Persistent cache across restarts.
- Named presets: Rain, Snow, Smoke, Film, Fire etc.
- Direct manipulation in Preview: drag position and resize with handles; avoid “sliders everywhere”.
- Modes: Chromakey / Luma Alpha / Screen Blend.
- Save chromakey/settings as named preset.
- Timeline: start/end points; current requirement is constant within its active interval.
- Preview must play the actual effect, not only a still frame.

## Subscribe
- Unlimited library and named presets.
- Direct drag/resize in Preview.
- Full animated preview.
- Schedule controls: first appearance, second appearance, repeat every X minutes.
- Timeline visualization.

## Library
Top navigation: Project / Render / Library / Settings. Library contains Effects / Subscribe / Ambient / presets and cache status.

## Outputs
- Final filename = project folder name + English suffix “Ready Videos”; never overwrite; add numeric suffix on collision.
- All outputs in one chosen folder.
- Timecodes in separate `timecodes` folder.
- Also create track-list `.txt` and technical project log.

## Startup/recovery
- Normal startup opens a clean Project page for speed.
- Queue state is persisted independently; if an interrupted queue is detected, show recovery notice and allow/automatically continue unfinished work after warning.

## Engine
- Automatic 10–20 sec benchmark on first run or when hardware changes.
- Windows candidates: NVENC / QSV / AMF / CPU fallback.
- macOS Apple Silicon: VideoToolbox first, CPU fallback.
- User normally does not select CPU/GPU manually.
- Full power by default. On Mac battery show warning but do not throttle automatically.
- Fast Engine diagnostics: Master-loop / Audio / Effects cache / Subscribe cache / Final mux timings.

## Distribution / licensing / updates
- Windows Setup.exe and macOS DMG.
- Goal: FFmpeg/FFprobe bundled for an offline render experience; internet only needed for activation/update checks.
- Activation screen on first launch if no key. Commercial monthly keys; owner lifetime key.
- App must never surface raw PowerShell/FFmpeg stack traces to user. Technical logs stay hidden; UI shows friendly actionable errors.
- Tauri updater for signed updates.

## Out of scope for 1.0
- Per-channel profiles (rejected by owner because number of channels is too high).
- Automatic YouTube competitor research/upload automation. Consider later as a separate module; it requires APIs/account management and source-data strategy per channel.
