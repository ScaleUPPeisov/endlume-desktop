ENDLUME 10.0.14 stable republish after macOS 15 Vision capture correction.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate: `38245502597` — PASS.
Authoritative signed exact-artifact physical gate: `38249457225` — PASS.
Signed source head: `39772360596b859f9e8bd2a495e3ae9f68eff533`.
Signed updater tar SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.

Real-updater run `38257188499` verified exact installed 10.0.13 baseline plus live 10.0.14 SHA/signature and correctly retried Vision attempts. It failed only because the release-only Swift harness used `CGDisplayCreateImage`, which is unavailable in the macOS 15 SDK. Mandatory rollback completed and live stable returned to exact 10.0.13.

Harness-only fix commit: `2f933ad88c9469b211f82c5e96a4a862b57b1957`. Screen capture now uses `/usr/sbin/screencapture`; Apple Vision reads the resulting PNG and the native updater state remains the acceptance oracle.

Republish the SAME accepted/signed 10.0.14 bytes rollback-safely, latest.json LAST, then rerun mandatory real updater acceptance.
