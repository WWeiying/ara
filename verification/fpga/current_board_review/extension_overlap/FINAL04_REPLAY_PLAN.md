# Final04 Replay: Awaiting Parent Freeze

Status: **HOLD**. No final04 replay or build has been launched. Start only after
the parent supplies the frozen image identity and notification. Do not rebuild
software, expand coverage, run combined144, or alter measurement01/matrix01.
The independent final03 successor service remains untouched and is not polled.

## Ordered Acceptance Gates

Use the unchanged `integration/run.py run`, one case per invocation, jobs1,
the same validated final04 image for every invocation, and new output directories.

1. Original-source port `extension_overlap_vl127`, programs directory
   `measurement01/build/soc`. **It must PASS before any matrix group starts.**
   Require its complete original oracle: full256 bytes including0xb26b tail,
   vstart0, guards, and all manifest PASS markers. A timeout or missing marker
   is not acceptance; stop and inspect evidence rather than advancing.
2. `extension_e16_m2_vf2`, programs directory `matrix01/soc`.
3. `extension_e32_m2_vf2`, same programs directory.
4. `extension_e64_m2_vf2`, same programs directory.
5. `extension_e32_m4_vf4`, same programs directory.
6. `extension_e64_m4_vf4`, same programs directory.
7. `extension_e64_m8_vf8`, same programs directory.

Each shape already executes24 consecutive trials without reset. Do not select
`all` or `extended` from either software manifest. Stop on an architectural
failure, retain the artifacts, and distinguish it from ongoing software progress
before considering a successor timeout. No RTL build is part of this plan.

## Software Pins

Paths below are relative to this directory. Revalidate the manifests and their
source/ELF hashes with the existing runner before execution.

| Artifact | SHA256 |
|---|---|
| measurement01/build/soc/programs.json | b782b143d26418aaac671e5377d50c86a3ee70b14d2edfd589b2db38c3cf495a |
| Original-source port ELF | c159c6e393697c6b3fb3456c956d1b33720f4188650da2323c7e2d88ffbd1960 |
| matrix01/soc/programs.json | 7760637359ea4104442176dcf8805c332b755d0189f2b3a1d5921a6f972cc5bb |
| extension_e16_m2_vf2.elf | a4112cc8e0414c43e1e49cefa2da80c53b48f67dfe029d0a11cd8e9229cd20c5 |
| extension_e32_m2_vf2.elf | 1b5edf24152275f0711bf7d004eb664c0e95cc1ba28e7e15678f1df9c1c194e5 |
| extension_e64_m2_vf2.elf | b1974e661d477edbbf58605b9b8d4f41395f3fc0e75f10d777986437b175dd93 |
| extension_e32_m4_vf4.elf | 6601d146b1367f513a527b86eda75ce00f5b7cd4775c1250ab48ff3e2f0c2512 |
| extension_e64_m4_vf4.elf | 97df9000f0e23926d934b60fdfdac42775e6269cd2a66dc2c690438939d66ba5 |
| extension_e64_m8_vf8.elf | 44819f88d2740018a9c65e9437e36c7611120a9614ef6fa200739e308f83d22e |

The original-source port is not the original Linux ELF. Its first acceptance
gate and the six derivative groups must remain separately identified in reports.
