ENDLUME 10.0.14 mandatory real updater acceptance — corrected UpdateExperience modal gate.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Authoritative signed physical gate run: `38249457225` — PASS.
Current rollback-safe republish run: `38253274117` — PASS.
Current live updater SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.

Previous updater run `38251417307` proved exact installed 10.0.13 baseline plus live 10.0.14 hash/signature, but the release-only harness searched the Settings button and never invoked the updater. Its mandatory rollback restored live stable and the physical Mac to exact 10.0.13.

The corrected gate launches installed 10.0.13, waits for its automatic UpdateExperience modal, presses exact `ОБНОВИТЬ`, exercises the normal signed Tauri updater, uses `RESTART ENDLUME` only if automatic restart has not already occurred, then runs full post-update VYRON / routing / Effects Preview / Subscribe Preview+final / production render acceptance. Any failure must restore exact 10.0.13 immediately.
