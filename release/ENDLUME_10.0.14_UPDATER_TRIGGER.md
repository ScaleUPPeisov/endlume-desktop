ENDLUME 10.0.14 mandatory REAL updater acceptance — Vision OCR physical gate.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Authoritative signed physical gate run: `38249457225` — PASS.
Current rollback-safe publish run: `38255790625` — PASS.
Current live updater SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.

Previous updater run `38253440237` failed only because macOS Accessibility did not expose the WebKit update button; mandatory rollback restored production and the physical Mac to exact 10.0.13.

Run the Vision OCR gate now: launch installed 10.0.13, physically click exact `ОБНОВИТЬ`, require native update-center state to enter DOWNLOADING/VERIFYING/INSTALLING, let the normal signed Tauri updater install/restart 10.0.14, then verify installed SHA/codesign/durable data and full VYRON / destination / Effects Preview / Subscribe Preview+final / production render acceptance. Any failure must restore exact 10.0.13 immediately.

Updater trigger: Vision acceptance retry after publish 38255790625.
