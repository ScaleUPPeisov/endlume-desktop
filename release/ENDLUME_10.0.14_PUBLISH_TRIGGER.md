ENDLUME 10.0.14 stable republish after Vision retry trap correction.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate: `38245502597` — PASS.
Authoritative signed exact-artifact physical gate: `38249457225` — PASS.
Signed source head: `39772360596b859f9e8bd2a495e3ae9f68eff533`.
Signed updater tar SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.

Latest real-updater run `38256202477` verified exact installed 10.0.13 baseline plus live 10.0.14 SHA/signature, but the release-only Vision harness inherited the global ERR rollback trap, so an expected early OCR miss triggered rollback before retrying. Rollback completed and live stable returned to exact 10.0.13.

Harness-only fix commit: `71dfd4b0903fee1f54b08afb26462ba35c097fc6`. Vision OCR misses are now retried normally; true updater failures still invoke immediate rollback.

Republish the SAME accepted/signed 10.0.14 bytes rollback-safely, with latest.json LAST, then rerun mandatory real updater acceptance.
