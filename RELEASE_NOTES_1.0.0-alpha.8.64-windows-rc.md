# ENDLUME YT Studio PEISOV 1.0.0-alpha.8.64 Windows RC

## Windows Turbo Renderer

This release continues from exact 8.63 source commit:

`a7a80bccc0a28221494ef6306177a388b2b5e4d6`

### Render core
- Preserve FAST_ONE_IMAGE / FAST_MULTI_STILL zero-copy MP4 sample-table architecture.
- Preserve 1920x1080, 60 FPS, HEVC/H.265 and yuv420p fast-output contract.
- Preserve Original Audio as MP3 packet-copy when input files are compatible.
- Direct Original MP3 concat-list packet-copy feeds the final mux without first writing a full intermediate playlist, removing one O(audio_bytes) write/read pass.
- The direct path is gated by a short packet-copy decode probe; if it fails, ENDLUME falls back to safe per-track packet-copy clean-remux with no lossy MP3 re-encode.
- Cached audio metadata probes read codec, sample rate, channels and duration in one FFprobe JSON call and are executed in bounded parallel batches.
- File-size ranges are targets only; Original Audio is not rejected or degraded merely for exceeding an artificial maximum.
- Final validation checks start/middle/end, the last 10 seconds and a real song-boundary seek/decode sample.
- Windows fast HEVC selection measures working NVENC / QSV / AMF candidates instead of assuming a fixed fastest vendor, then persists the choice against a GPU/driver fingerprint.
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
- Compact first-start completion notice is shown only after a real version change and includes the local Homer mascot.
- Windows installation UI does not fake a same-process completion screen: Windows may close ENDLUME when the installer starts, and completion is confirmed on first launch of the new version.

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
