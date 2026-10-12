ENDLUME 10.0.14 mandatory real updater acceptance retry from restored exact 10.0.13 baseline.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Signed physical gate run: `38249457225` — PASS.
Final republish run: `38251306256` — PASS.
Republish source head: `f0665e9492c8760d2a1cc70e8d4d4078e0008734`.
Live latest.json after republish: `10.0.14`.
Live macOS updater SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.

First updater run `38250960083` failed before the normal update path because the physical `/Applications` baseline was not exact 10.0.13. Its mandatory rollback completed: live production returned to 10.0.13 and the physical app was restored from the verified 10.0.13 rollback tar. The same accepted/signed 10.0.14 bytes have now been republished successfully.

Run the NORMAL installed ENDLUME 10.0.13 -> 10.0.14 updater path now, then post-update physical smoke. On any failure restore production and physical installation to verified 10.0.13 immediately.
