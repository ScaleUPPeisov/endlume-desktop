ENDLUME 10.0.14 signed packaged physical gate trigger — exact signed updater artifact QA.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate run: `38245502597` — PASS.
Previous signed gate run `38248605878`: build PASS, codesign PASS, updater signature PASS, packaged UI launch PASS, durable owner state preserved; it failed only because QA referenced the transient Cargo bundle executable after macOS resolved the app to `/Applications`, before VYRON/render QA started.

This run extracts the freshly signed updater `.tar.gz`, verifies its exact 10.0.14 ARM64 app/codesign, and executes VYRON + Effects Preview + Subscribe Preview/final + production render QA against those exact bytes. Functional product source remains frozen.
