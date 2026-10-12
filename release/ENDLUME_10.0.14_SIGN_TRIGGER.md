ENDLUME 10.0.14 signed packaged physical gate trigger — hardened exact executable launch.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate run: `38245502597` — PASS.
Previous signed gate run `38246222874`: build PASS, codesign PASS, updater signature PASS; QA launch harness failed because `open/pgrep` could not resolve the packaged process identity.

Retry launches the exact executable inside the freshly built `.app` directly. Functional product source remains frozen.
