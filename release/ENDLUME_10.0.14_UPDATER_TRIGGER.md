ENDLUME 10.0.14 mandatory REAL updater acceptance — post-wrapper-fix final gate.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Authoritative signed physical gate run: `38249457225` — PASS.
Current rollback-safe publish run: `38260893930` — PASS.
Current live updater SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.
Updater wrapper syntax fix: `3a19c25dbdb94908db78e542656f8eee96e8831b`.
Mandatory pre-retry rollback to exact 10.0.13: run `38260545160` — PASS.

Run installed 10.0.13 through the NORMAL signed Tauri updater path to 10.0.14. Require download, signature verification, install, restart, installed version 10.0.14, preserved durable user data/settings, and full post-update VYRON / destination / Effects Preview / Subscribe Preview+final / production render acceptance. Any failure must restore exact 10.0.13 immediately.
