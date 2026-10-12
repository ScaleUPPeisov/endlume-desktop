ENDLUME 10.0.14 signed packaged physical gate trigger — signed updater payload QA retry.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate run: `38245502597` — PASS.
Previous signed gate run `38248605878`: build PASS, codesign PASS, updater signature PASS, packaged execution PASS, durable owner state preserved; QA failed before VYRON because it referenced the transient Cargo bundle path.

This retry extracts the freshly signed updater `.tar.gz`, verifies its exact 10.0.14 ARM64 app and codesign, then executes VYRON routing, Effects Preview, Subscribe Preview/final and production render QA against those exact signed payload bytes. Functional product source remains frozen.
