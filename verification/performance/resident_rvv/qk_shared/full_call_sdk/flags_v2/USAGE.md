# Corrected SDK Functional Gate

This directory publishes the eight helper files from the immutable
`stage3_attention_sdk_build_20261110_02/inputs/fixture/` byte for byte. `USAGE.md`
is the only additional file. The original parent-directory six helpers remain
historical build01 inputs; do not use their combined PV/preparation flag model.

The authoritative existing firmware is:

`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage3_attention_sdk_build_20261110_02`

Its receipt SHA is `ac91488d3ea3836121973fa2ecf54c5ef34a7798b1b510dbb2941d8bdedabd81`;
261 source pins SHA `1d63af8545837bb63e0475ac489eeddbdfb8576a56b22a9ef2da3f9b4840f099`.
ELF SHA `d8c413799646ddf3286347d0c18a76eaaadce27a2840fc3bf4f46f3d7d1de17c`.
Publication does not change that inventory, rebuild firmware, or authorize VCS.
Parfit's separately owned runner stays bound to the BUILD02 checker snapshots.

## Entry Points

```sh
python3 -B verification/performance/resident_rvv/qk_shared/full_call_sdk/flags_v2/test_sdk.py -v
python3 -B verification/performance/resident_rvv/qk_shared/full_call_sdk/flags_v2/check.py \
  --build BUILD02 --log LOG --vector VECTOR_CSV --commit COMMIT_CSV
```

The checker must import this directory's `fixture.py`, not a cached historical
module. It deliberately returns `protocol_checked=false`: the runner must also
pass the strict independent zero-exception protocol checker and post-run source/
image identity checks. The existing firmware needs no new build, but reviewed
preparation alone does not close gate F: actual SDK execution and all terminal
checks must pass. `build_flags_v2.py` in the parent directory records the
explicit predecessor-to-successor transformation. The copied
`flags-v2-contract.json` retains its original absolute provenance paths on purpose.

## Contracts And Evidence

Three calls all use the same enabled experimental SDK entry with requested
0/1/1 and automatic1: OFF original D128/H2/T137, ON original seeded DZ=8,
ON derived D96/H3x2/T65. OFF is functional fallback, not a performance baseline.
Global natural flags remain3 and FCSR is 3/11/3. PV_PREP counts software casts,
seed rescale and coefficient conversion; PV counts only token-ordered hardware
FMAs. The 18-test log includes prep-only NX with hardware flags0 and rejects
hardware probes that claim preparation NX or incoming DZ.

Frozen host log: BUILD02/hosttests.log, SHA
`9ae26d1a3f797ccf14fa79ce96262e6aaff2a976cfd4514bde90f9856b2baaaa`.
Derived scalar expf has exactly six +0 inputs, each producing exact1 and flags0;
no new nontrivial glibc/newlib equivalence or Spike probe is required. The four
nonzero original samples remain covered by the unchanged accepted original
tile64 golden SHA; this is not a general libm equivalence claim.

The three calls check 1088 raw F32 outputs: 256/256/576. The two original goldens
have SHA `0be0c9b07fdbd8773ec85ef2b738bbcc65f657f322d65e77610609c968ee9316`.
The independently recomputed derived golden has SHA
`19f95bebaac1071ae2b93a5e9cdfdd3c7a9dacbca7223f6d87dbe82d2864470e`.

Quality proof remains at OUT/stage3_attention_sdk_fixture_quality_20261110_01:
six host tests PASS; six unique active F16 query rows and six unique output-head
fingerprints; two distinct active K groups and V groups. Four wrong-base/stale
FULL mutations change all96 outputs of every affected head, leaving unaffected
heads identical. Query dimensions rotate7*h; KV token rows rotate64*g before
cropping65. These are labeled model-data-derived rows/groups, not six captured
model heads. No extra target case or RTL experiment was added.

Required work is 247 legacy commands (237/4/6), 11 QK and 11 PV commands,
255 vector custom allocations (233 native +22 resident), and actual retired
entry counts decode_execute6 (including three pure preflights) / SDK executor4.
The terminal `stage3_attention_sdk_vcs_20261110_01/result.json` now verifies
these counts, all 1,088 exact outputs, FCSR 3/11/3, guards and post-run identities.
Independent protocol passes with zero exceptions, errors or outstanding work.
This is scoped actual SDK functional acceptance, not a new performance or
deployment claim. The result SHA256 is
`70ccad29ade83850f3c6a94276b8f60d7258513c4091939267641f550bbd3fb1`.

All published sources are frozen for parent review/commit. No production files,
old helper, frozen OUT file, checker threshold, or numerical contract was changed.
