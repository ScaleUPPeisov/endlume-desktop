ENDLUME 10.0.14 signed packaged physical gate trigger — post-fork packaged child verification.

Functional source: `55372b94a35ef76ee160347783cf8c62e003fa4e`
Release commit: `b2d3ea03a3c5ecd0293df83260d0c35f2a54bcc9`
Compile gate run: `38245502597` — PASS.
Previous signed gate run `38248190978`: build PASS, codesign PASS, updater signature PASS; runner cleanup again observed the forked `endlume` child after the transient launcher PID exited.

Retry waits for fork/re-exec and prefers the new child PID. Functional product source remains frozen.
