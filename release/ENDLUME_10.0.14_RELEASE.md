# ENDLUME YT Studio PEISOV 10.0.14 — Stable Release Record

Release version: 10.0.14

Functional source:
`55372b94a35ef76ee160347783cf8c62e003fa4e`

Physical acceptance run:
`38231795588`

Physical acceptance source:
`6b785bbdb71a563291ab3285b82a09e24904d175`

Persisted accepted-source commit:
`55372b94a35ef76ee160347783cf8c62e003fa4e`

Owner authorization:
`RELEASE 10.0.14 APPROVED`

## Accepted physical results

- VYRON -> TOSHIBA routing: PASS
- different channels -> different output folders: PASS
- cross-write: NONE
- Effects Preview: PASS
- Subscribe Preview: PASS
- Subscribe in final output: PASS
- Round Equalizer: PASS
- other effects: PASS
- HEVC: PASS
- 1920x1080: PASS
- 60 FPS: PASS
- AAC: PASS
- 48 kHz: PASS
- stereo: PASS
- beginning/middle/end decode checks: PASS
- distribution size contract 400-600 MiB: PASS
- finalizer target: 450 MiB
- warm production render: 7.043 sec
- VYRON physical render: 6.990 sec

## Frozen release contract

ENDLUME 10.0.14 is a release/packaging operation from the functional source above. Functional product source remains frozen. Release preparation may change version metadata, lockfile package-version metadata, release records, and dedicated 10.0.14 release pipeline files only.

Production updater target remains:

- repository: `ScaleUPPeisov/scaleup-site`
- release tag: `endlume-stable`
- application identifier: `studio.endlume.desktop`
- updater endpoint: `https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/latest.json`

Historical ENDLUME 10.0.13 release records and workflows remain unchanged for audit/rollback.
