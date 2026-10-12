ENDLUME 10.0.14 mandatory REAL updater acceptance — final macOS 15 Vision + rollback-hardened gate.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Authoritative signed physical gate run: `38249457225` — PASS.
Current recovery/rollback-safe publish run: `38258239049` — PASS.
Current live updater SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.

Vision capture is macOS 15 compatible via `/usr/sbin/screencapture` + Apple Vision PNG OCR. Expected OCR misses retry normally. Updater acceptance is valid only after native update-center state enters DOWNLOADING/VERIFYING/INSTALLING or later.

Emergency rollback is now retry-hardened: canonical 10.0.13 tar/signature and latest.json are uploaded with retries and then publicly re-fetched and verified before rollback is considered complete.

Launch the installed 10.0.13, use the normal signed Tauri updater to install/restart 10.0.14, verify exact installed SHA/codesign/durable data, then run full VYRON / correct destination / Effects Preview / Subscribe Preview+final / production render acceptance. Any failure must restore and verify exact 10.0.13 immediately.

Final updater trigger after publish 38258239049.
