ENDLUME 10.0.14 mandatory real updater acceptance trigger.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Signed physical gate run: `38249457225` — PASS.
Publish run: `38250697018` — PASS.
Published head: `750ce10bcd7481bc26d4f606bf34c3a6d055fb77`.
Live latest.json: `10.0.14`.
Live macOS updater SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.
10.0.13 rollback evidence: run `38250697018`, artifact `ENDLUME-10.0.13-STABLE-ROLLBACK`, artifact ID `11746793695`.

Run only the normal installed ENDLUME 10.0.13 updater path to 10.0.14, then post-update physical smoke. On any failure restore production and physical installation to verified 10.0.13 immediately.
