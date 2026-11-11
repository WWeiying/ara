# QEMU Bundle Source Audit

Source-only audit, 2026-11-10. Not a rebuild, guest run or Stage5 acceptance.
`OUT` below is `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out`.

Exact inputs copied from `OUT/stage5_qemu_delivery_20261110_02/`:

| Repository file under `qemu_bundle/` | Bytes | SHA256 |
| --- | ---: | --- |
| manifest.json | 98528 | a7dcb9001a995bfbd886e327b334561f1aa2a5158dadf0abbaf721064a2e5148 |
| payload.tar.xz | 255016 | ce4f9ffde30105afe139f84ce116486d4749273fc871363eff9e188700f720b9 |

Manifest was transferred through apply_patch without reserialization; the binary
payload was copied from the artifact. Both must remain byte-identical to source.
The original capture receipt is retained in OUT, SHA256
`4019da7ecae5ae4524c151bd0e4c92775552b738d3e6ba306e3f65bbbccd7586`.
Its state is `SOURCE_DELTA_REPLAY_CHECKED_NOT_REBUILT`.

Read-only audit used unchanged `delivery/qemu_source.py`, SHA256
`a9d252d5501e6adb3be8164648d866b1310345888d124f094d25c1f4ec4e7978`:

- All 338 content-addressed payload blobs match their names and manifest sizes;
  no extra, duplicate, missing or non-regular payload members are accepted.
- All manifest postimages match the actual variant04 tree. Its complete inventory
  matches: 84955 entries, 78571 files, 6312 directories, 72 symlinks; inventory
  SHA256 `164d0a470c70b2d524956608c7aeb0533ab503b797f749978931838647c1bc56`.
- Origin is `OUT/stage5_qemu_prepare_variant_20261110_04/prepare.json`, SHA256
  `17272253837fe18a89725dbe01e1ec59dee9a6d117ce5ad27e25bbcc99bcb17f`.
  This equals both manifest provenance and BUILD07's prepare identity.
- `OUT/stage5_qemu_build_20261110_07/build.json`, SHA256
  `85a4939f7419c706280f6959c89a25f322f6bf5b0caf7c3bb7c1c60b7305c701`,
  explicitly builds variant04 and records post-build pins unchanged. Its image
  identity is `1f4619e1573ed6626b259912d6780ac9d40e8cca8ed38ec32694a0b1d399388a`.
  That binary is NOT included here or newly validated by this packaging audit.

The original capture checked full primary-to-final delta replay. This audit
checks the existing capture, payload and current final-tree identity; it does
not repeat full primary extraction/reconstruction. The exact EDK2 unsafe-link
exclusion and only the two exact empty generated entries are preserved.
The DTC 310-file provenance/mode exception remains explicit in the manifest.

Before edits, the active `stage5_qemu_execution_20261110_03/source-pins.json`
was inspected, including documentation keys. No new destination is pinned.
Existing README, source tools, sourcebundle and consumer inputs were not edited.
No compiler, RTL, QEMU or model execution was started.

Post-transfer validation: both SHA256 values above match the original capture;
13 `test_qemu_source` unit tests pass under Python3.11 with ResourceWarning
treated as an error. These tests use tiny synthetic archives, not a full rebuild.
