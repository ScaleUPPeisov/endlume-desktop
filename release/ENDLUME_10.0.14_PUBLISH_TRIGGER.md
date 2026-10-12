ENDLUME 10.0.14 stable publish retry.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate: `38245502597` — PASS.
Signed exact-artifact physical gate: `38249457225` — PASS.
Signed source head: `39772360596b859f9e8bd2a495e3ae9f68eff533`.
Signed updater tar SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.

Previous publish run `38250268231` stopped before 10.0.14 mutation because the pre-release live latest.json unexpectedly reported 10.0.12. Exact live pre-release state was preserved. This retry also prepares an owner-intended 10.0.13 rollback channel from the immutable versioned 10.0.13 tar/signature before publishing 10.0.14.

latest.json must remain the last stable asset switched.
