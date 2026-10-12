ENDLUME 10.0.14 signed packaged physical gate trigger — fork-aware packaged process detection.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate run: `38245502597` — PASS.
Previous signed gate run `38247648302`: build PASS, codesign PASS, updater signature PASS; packaged executable forked/re-execed and the harness checked the transient launcher PID while a new `endlume` child remained alive.

Retry detects the new packaged child PID after launch. Functional product source remains frozen.
