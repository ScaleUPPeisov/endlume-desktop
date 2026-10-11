# ENDLUME 10.0.13 Release Record

- Release version: 10.0.13
- Source engine head: `e4a07972b1566ed73b11c4eb758d59f4dc839e71`
- Canonical base: `3f06c7329bd3821bc160e6d88c5b294fc0d82c2b`
- Fast Engine source: `a7a399e83de8b9248e2065c6dda1f9079ded6565`
- Phase 3 source artifact: `11677270291`
- Phase 3 final diagnostic evidence: `11693338342`
- Owner authorization: RELEASE 10.0.13 APPROVED

## Accepted physical qualification

- Static 3h: 2.5135 s, 437.255 MB, HEVC 1080p60, MP3 packet-copy, decode/seek/DTS PASS.
- Periodic 3h: 5.8622 s, 437.279 MB, phase/seam/decode/seek/DTS PASS.
- Subscribe 3h: 3.1270 s, 437.394 MB, timing/decode/seek/DTS PASS.
- Combined: 22.180 s, informational performance warning only.
- Normalize/Crossfade/Unsupported visual fallbacks: PASS.

## Accepted known issue

`KNOWN_PREVIEW_ONLY_PERIODIC_BOUNDARY_ISSUE`: canonical Preview frame 299/300 at 4.983333333 s has MAE 8.5345293, while Fast-render output matches expected source frame 299 at MAE ~0.03263. Export is phase-correct. Follow-up: #27 for 10.0.14.
