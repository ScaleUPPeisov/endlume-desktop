ENDLUME 10.0.14 stable republish after mandatory rollback and updater-wrapper syntax correction.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate: `38245502597` — PASS.
Authoritative signed exact-artifact physical gate: `38249457225` — PASS.
Signed updater tar SHA256: `f84a321fe90f833b4a50edd20851fe9ac4f999b85d5272d2e6f3ffd3f13d5c78`.

Mandatory rollback run `38260545160` is GREEN and restored live production to exact 10.0.13 before retry.
Updater acceptance run `38258676785` failed before executing the updater because release-only wrapper `phase4_physical_update_1014_final.sh` had an unterminated Python triple-quoted string. Wrapper fix commit: `3a19c25dbdb94908db78e542656f8eee96e8831b`.

Republish the SAME fresh signed 10.0.14 candidate, preserving a new exact 10.0.13 rollback snapshot, validating public bytes, and switching latest.json LAST. Then run mandatory real installed 10.0.13 -> 10.0.14 updater acceptance.
