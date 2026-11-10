# SDK Whole-Call Functional Gate

Prepare/build only. No simulation is launched by these helpers.

Three calls use real `akv_decode_execute` and the SAME enabled experimental SDK
entry, automatic policy 1, without `--wrap`:

| Call | requested | D | Query/KV heads | T | Incoming fflags |
| --- | --- | --- | --- | --- | --- |
| OFF original | 0 | 128 | 2/1 | 137 | 0 |
| ON original | 1 | 128 | 2/1 | 137 | DZ=8 |
| ON derived | 1 | 96 | 6/2, two H3 groups | 65 | 0 |

Platform admission and whole-call ownership are asserted for all three calls.
The owner preflights every group and workspace nonaliasing before the first FULL.
Plans already include global offsets; the callback passes them unchanged. Derived
groups have first_head 0/3, with local pair bases 0/2 and H2/H1 on each tile64/1.
All QK pairs precede existing C softmax; all PV pairs finish before the next REFILL.

Original data retains the frozen Qwen3 capture identity. Derived Q row h uses
captured row h%2, rotating dimensions by 7*h; only the first96 are active. KV
groups use captured tokens0..64 and64..128 respectively, retaining physical
128-halfword row strides. Mask is first65 and scale is unchanged. These are
labeled derived head rows, not a claim of a newly captured D96/H3 model layer.

`fixture.py` recomputes both shapes using independent Spike SoftFloat: ascending
F32 QK dimensions, the existing C softmax approximation/online update, and
token-ordered F16 PV. Scalar expf uses pinned host libm, matching the accepted
tile64 C reference. Positive F64 reduction error bounds must give one F32 sum
regardless of reduction tree. Original output must reproduce accepted SHA
`0be0c9b07fdbd8773ec85ef2b738bbcc65f657f322d65e77610609c968ee9316`.
Natural flags are independently accumulated, including query conversion and
preparation; final expected flags are natural OR incoming. Caller CSR setup is
outside ROI; SDK/leaf never clear flags. Host checker reads every output raw bit,
full input/query fingerprints, outer guards, inactive D/head workspace/output,
FCSR/frm/vcsr/vstart, group offsets and unique terminal records.

Build inputs are Git archive 8dc915db8689d801af991676c25b75093bec9a4b SDK/common,
plus ONLY the approved frozen native C and new executor header from executor
host02. Archived qk.S/pv.S/prep identities are checked. The dirty root v2 assembly
and broad host-test inventories are excluded; assembly SHA is explicitly
0e90dccf193c43bcda367fa18813bedb1077e9790795635f9efa993871a20061.
Fresh compile uses GNU rv64gcv_zfh_zvfh, four lanes/VLEN1024, strict FP, overlap0,
experimental macro1. No separate prep object or second native C object is linked.

```sh
python3 -B verification/performance/resident_rvv/qk_shared/full_call_sdk/test_sdk.py -v
python3 -B verification/performance/resident_rvv/qk_shared/full_call_sdk/build.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage3_attention_sdk_build_20261110_01
```

Work checks require 247 legacy command completions (237/4/6), 11 QK+11 PV,
exact ordered opcode signatures, command-local arithmetic flags, four-lane FMA
counts and source/result/final-ack geometry, architectural write masks and actual
ELF-bound SDK entry retires (four groups; six decode calls including pure
preflights). Generic EEW maintenance is NOT assumed globally serial. A later
reviewed runner must bind the accepted historical SoC/image pins and run the
unchanged strict independent protocol checker with zero expected exceptions;
`check.py` deliberately returns protocol_checked=false. Required plusargs include
AKV_PERF/SUMMARY and RESIDENT_QK_PERF/PV_PERF/PV_WATCHDOG. No acceptance until
that independent protocol and post-run pins/image check also pass.

OFF/native timing is functional diagnostic only, NOT a performance baseline.
Strong-baseline performance belongs to the separate Stage E ABBA. This gate is
not GGML integration, capability advertising, production enablement or a speedup
claim. Eventual single SoC run is separately authorized and bounded below1h.

## PV Counter Boundary Successor

This explicit successor preserves build01 and all original helpers. PV_PREP
contains software alpha cast, seed rescale and probability casts. PV contains
only token-ordered hardware FMAs; hardware probes exclude both preparation
and incoming sticky flags. Whole-call natural flags/outputs are unchanged.
The six derived scalar expf inputs must all be +0, yielding exact1 and flags0;
any other derived sample stops preparation pending target-libm evidence.
Original golden SHA regression is not general glibc/newlib equivalence.
Use test_sdk.py for all18 tests (including the new phase/mutation tests).
