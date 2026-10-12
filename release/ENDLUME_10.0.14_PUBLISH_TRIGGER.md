ENDLUME 10.0.14 stable republish after mandatory updater baseline rollback.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate: `38245502597` — PASS.
Signed exact-artifact physical gate: `38249457225` — PASS.
Signed source head: `39772360596b859f9e8bd2a495e3ae9f68eff533`.
Signed updater tar SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.

Publish run `38250697018` was PASS, then mandatory updater run `38250960083` failed before normal update because the physical baseline was not exact 10.0.13. Its rollback completed successfully: production live version returned to 10.0.13 and `/Applications/ENDLUME YT Studio PEISOV.app` was restored from the verified 10.0.13 rollback package.

Republish the SAME accepted/signed 10.0.14 bytes rollback-safely. Keep latest.json LAST. Then repeat the real installed 10.0.13 -> 10.0.14 updater acceptance.
