ENDLUME 10.0.14 stable recovery + republish after macOS 15 Vision capture correction.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate: `38245502597` — PASS.
Authoritative signed exact-artifact physical gate: `38249457225` — PASS.
Signed updater tar SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.

Real-updater run `38257188499` failed only in the release-only Vision capture API and rolled live latest back to 10.0.13. GitHub Releases transient HTTP 500 during that rollback left the canonical 10.0.13 generic tar missing while latest.json already pointed back to 10.0.13.

Recovery publisher commit: `55bf01250cef637b2ca8fa4a7d880d64212e5cf7`. Before any 10.0.14 mutation it now restores/verifies the exact canonical 10.0.13 channel from rollback artifact run `38257054613` if needed, then uses retry-hardened GitHub release uploads. latest.json remains LAST.

Vision capture fix: `2f933ad88c9469b211f82c5e96a4a862b57b1957` uses `/usr/sbin/screencapture` + Apple Vision on the PNG.

Recover 10.0.13 baseline first, republish the SAME signed 10.0.14 bytes, then rerun mandatory real updater acceptance.
