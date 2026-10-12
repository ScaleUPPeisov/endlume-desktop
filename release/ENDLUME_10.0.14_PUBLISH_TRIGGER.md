ENDLUME 10.0.14 stable republish for Vision-driven real updater acceptance.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate: `38245502597` — PASS.
Authoritative signed exact-artifact physical gate: `38249457225` — PASS.
Signed source head: `39772360596b859f9e8bd2a495e3ae9f68eff533`.
Signed updater tar SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.

Previous real-updater run `38253440237` failed only because macOS Accessibility could not expose the WebKit update button. Its mandatory rollback completed and production returned to exact 10.0.13.

Republish the SAME accepted/signed 10.0.14 bytes rollback-safely, latest.json LAST. Then run the Vision OCR physical gate, requiring the native updater state to enter DOWNLOADING/VERIFYING/INSTALLING before accepting the click, followed by installed-version/restart/data/VYRON/Preview/Subscribe/render acceptance.

Republish trigger: Vision gate retry 2026-10-12.
