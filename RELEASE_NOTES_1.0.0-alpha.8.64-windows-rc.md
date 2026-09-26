# ENDLUME YT Studio PEISOV 1.0.0-alpha.8.64 Windows RC

## Windows Turbo Renderer

This release continues from exact 8.63 source commit:

`a7a80bccc0a28221494ef6306177a388b2b5e4d6`

### Render core
- Preserve FAST_ONE_IMAGE / FAST_MULTI_STILL zero-copy MP4 sample-table architecture.
- Preserve 1920x1080, 60 FPS, HEVC/H.265 and yuv420p fast-output contract.
- Preserve Original Audio as MP3 packet-copy when input files are compatible.
- Direct Original MP3 packet-copy concat is attempted first to remove redundant per-track full-file remux I/O.
- If direct concat fails integrity/duration validation, ENDLUME falls back to safe per-track packet-copy clean-remux; there is still no lossy MP3 re-encode.
- Combined cached audio metadata probe reads codec, sample rate, channels and duration in one FFprobe JSON call.
- Windows fast HEVC selection measures working NVENC / QSV / AMF candidates instead of assuming a fixed fastest vendor.
- FFmpeg and FFprobe launch counts are emitted in engine telemetry.
- Added project-scan, audio-probe, audio-preparation, encoder-detection, validation and side-files timings.
- Added physicalEncodedFrames, logicalFrames and manifestFrames evidence.
- No synthetic file padding.

### Update experience
- Full-window update experience inside ENDLUME instead of the small popup.
- Local Homer mascot asset is bundled into the production frontend.
- Startup splash runs while normal initialization is happening; no artificial sleep is added.
- Update page shows current/new version, release changes and update date.
- Download UI is connected to real updater state and reports downloaded bytes, total bytes, measured speed and ETA.
- Physical updater states: DOWNLOADING, VERIFYING, READY_TO_INSTALL, INSTALLING, RESTART_REQUIRED and FAILED.
- Existing signed updater remains the backend.
- SHA-256 mismatch blocks installation.
- Compact first-start notice is shown once per installed version.

### Release status
- RC only.
- Stable promotion is forbidden until real Windows 10/11 hardware acceptance is complete.
- Required performance acceptance remains:
  - 1 hour: target <= 7 s
  - 2 hours: target <= 10 s
  - 3 hours: target <= 15 s
  - 2 hour multi-still: target <= 15 s
- Five consecutive runs are required for each acceptance project.
- Never report a hardware PASS when the corresponding real test was not executed.
