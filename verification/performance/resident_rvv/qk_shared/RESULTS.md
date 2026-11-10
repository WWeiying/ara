# Stage-3 Component Checkpoint

The implementation extends the existing resident PV datapath with FP32 QK
accumulation on the actual lane FPU. It reuses the lane-private 16 x 64-bit
accumulator array, the two reader entries and existing AKV Q/K/V storage.
No new arithmetic array, larger SRAM or wider external interface is introduced.
QK and PV remain experimental and unadvertised; normal runtime selection is
unchanged. This checkpoint does not establish complete Attention performance.

## Checked Evidence

All paths below are relative to
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`.

| Gate | Receipt | Verified scope |
|---|---|---|
| Original CPU dirty-state cause | `resident_pv_commit_dirty_20261110_03/report.json` | 72 WT/WB checks; original 23 dirty-state failures versus zero after the patch; other outputs equal. Original PV SoC reproducer still pending. |
| Synchronous resident reader | `stage3_reader_gate_20261110_01/report.json` | 232 normal scenarios, 128,048 accepted-data checks; four each of cancel/reset/invalid-command cases; real context and synchronous storage. |
| Central control and final-write accounting | `stage3_control_gate_20261110_03/report.json` | 43 scenarios, 12,078 checks; tagged stub lanes, stalled final acknowledgements and outstanding K-collector drain. Not an arithmetic test. |
| Actual shared FPU | `resident_qk_lane_fpu_20261110_01/report.json` | Standard/shared integer configurations each pass 26 controller scenarios against independent SoftFloat expectations and the unchanged ordinary-FP/coexistence suite. |
| Decoder and ABI | `qk_admission/test_admission.py` | 17 host tests, exhaustive control/register checks, default-off selection, no VRF source, preserved old operation IDs and generated contracts. Not whole-SoC execution. |

The FPU gate checks FP32 QK and existing FP16 PV, all five supported rounding
modes, signaling/quiet NaNs, inactive elements, odd tails, held outputs,
abort/drain, reset cancellation and reacquisition by QBS. Per arithmetic
configuration, 6,302 operations are accepted, 6,298 return, and four are
explicitly cancelled by reset. The original full-FP suite retains its checker.

The control gate holds ownership until the final accepted writes return their
acknowledgements. Cancellation during an uncancellable K gather retains the
lease until that gather drains. Its first two attempts remain recorded: both
failed testbench expectations, not proven RTL arithmetic failures. The third
attempt corrects the hexadecimal sentinel and the single-active-lane barrier
expectation without weakening completion, data or ownership checks.

Receipt SHA256 values at review:

```text
CPU:     2b297b1738ba1aea7e539a83ac6ade6dfd624168590d804fb211dec285b4872d
Reader:  ee15e86c3f52ff66c0acefda7bcb098e94d97a41e8f70ca31202481dbc6c2458
Control: b0099f9f0df97248f0147234e807dc828fd9736ebd3d6192c52349dc31d86e59
FPU:     f3673a5d5b406c7662b9378dc8cc7cdab11638543dcbfa02bbb54bc237459ef8
```

## Complete-Call Preparation

The smoke and ABBA firmware builds are complete, not executed:

- `stage3_attention_build_smoke_20261110_01/build.json`
- `stage3_attention_build_abba_20261110_01/build.json`

Both use the frozen real Attention input, D128, two query heads and 137 context
tokens split into 64, 64 and 9. The baseline retains panel-four RVV QK and
rotating-register PV. The candidate replaces both arithmetic leaves while
keeping preparation, online softmax, rescaling, normalization and final drain.
The unchanged oracle requires all output bits, flags and memory guards to match.
The new work checker additionally checks every resident operation, per-lane
accepted/returned FMA count, output byte-enable and architectural write.

## Still Required

1. Re-run the exact original PV boundary ELF, then QK architectural boundaries.
   The fresh image described below has built successfully; build completion is
   not functional acceptance.
2. Pass complete-call smoke before paired ABBA measurements. Report full-call
   cycles separately from resident-engine cycles; do not infer model speedup.
3. Make a measured retention decision and complete applicable runtime/fallback
   integration and version delivery. No FPGA or physical acceptance is implied.

## SoC Build and Architectural Firmware Checkpoint

`stage3_soc_20261110_02/build.json` records a successful VCS build from
`9af19508de139641ea561ccdbd3114eba4007c6e` plus the reviewed CPU retirement
overlay. The 52-file simulator image includes nine shared libraries. Its 380
dependency files match the accepted closure except for that exact CPU overlay;
no live dirty dependency files were compiled. Configuration remains four lanes,
VLEN1024, 16 MiB simulation L2, shared integer multiplier enabled, shared FMA
and stage-two borrowing disabled, resident QK/PV enabled, capability zero.
The 17 builder host tests pass. The 127 compile warnings match the earlier
PV build, excluding two approved duplicate-file warnings removed from its
file list. No new compile error or fatal was observed.

The original PV firmware is now assigned to
`stage3_pv_boundary_20261110_01`. Execution has finished: the unchanged firmware
reports 21 successful cases, 12 expected rejections and zero errors, and the
independent protocol report passes. The original overall result remains FAIL:
the sealed work checker requires globally serial backend micro-operations.
The mixed-layout case instead allocates independent maintenance operations to
different VIDs before either completes.

At architectural sequence 926, v8/VID0 is allocated at cycle 3,088,673 and
v9/VID1 at 3,088,674; their completions occur at 3,088,688 and 3,088,696.
The following v10/v11 and v12/v13 pairs likewise overlap. All six maintenance
operations write the expected source bits through SLDU. The final PV allocates
at 3,088,748, after the last maintenance completion at 3,088,746. Independent
read-only review finds no live-VID reuse, unowned write or missing completion.
The original numerical and architectural checks also pass in a diagnostic
replay that splits by live VID allocation generation instead of one global
live slot. This diagnostic is not a replacement for the original worker result.
A separate successor audit with negative tests is being prepared; no new RTL
change or simulator rerun is justified by this parser failure.

`resident_qk_boundary_build_20261110_01/build.json` records the separately
frozen QK firmware, with 30 passing host tests bound to its actual GNU-built
ELF. Independent review checked all 165 source pins and 158 artifacts. This
is 23 scenarios, 35 direct attempts plus one helper call: the expected totals
are 24 successful QK retirements and 12 real traps, not executed results yet.
The query-bound case uses base6/H2 against seven loaded rows, followed by
base5/H2 recovery in the same context. It therefore distinguishes runtime
context rejection from the separate architectural eight-row limit.

```text
QK build receipt: f660436c74629b8cc2055ea3387e362538b530f76a4884cec98dfbedda515af2
QK ELF:          d7823dca2c700174223629df36a7dc65de1828ee313e7219d57a059c0b5bc7fa
```

The first QK runner preparation stopped before simulator launch because it
expected `configuration.cpu_retirement_overlay`, while the checked SoC receipt
stores `cpu_overlay` at its top level. The failure is preserved in
`resident_qk_boundary_vcs_20261110_01/PREPARE_FAILURE.md`. The frozen firmware,
original runner and numerical checks are preserved; a separately reviewed
successor must use the actual stage-three build contract. This preparation
failure is not an RTL failure or architectural acceptance.

The reviewed successor `qk_boundary_soc_v2.py` now uses the same strict
`build_soc.checked_build()` contract as the original PV successor. It copies
the unchanged frozen QK numerical/architectural checkers and the independent
protocol package. It also records an explicit runtime environment and checks
dynamic library resolution without executing the simulator.
`stage3_qk_boundary_v2_20261110_01/prepare-report.json` is
`PREPARED_NOT_EXECUTED`: 15 adapter tests and the original 30 firmware tests
pass, and independent review verifies 912 pins and 44 frozen inputs. Inventory
SHA256 is `bbb07a73d743732f5c530c0e9e938ad38d660c9fcdb1aedb209772c52e1bbc92`.
The expected exception counts remain ten accelerator rejections and two
CPU-only FS/VS-Off rejections. The prepared successor has now been launched:
its direct-owned service is
`resident-qk-boundary-v2-stage3_qk_boundary_v2_20261110_01.service` and the actual
`stage3_soc_20261110_02/sim/simv` was confirmed executing the frozen QK ELF.
This independent boundary run proceeds while the separate PV parser audit is
finalized; it does not promote gate A or bypass its acceptance requirement.
No QK hardware PASS is claimed while its worker is pending.

## CPU Patch Delivery Preparation

`stage3_cva6_dirty_delivery_host_20261110_01/report.json` records 31 passing
host checks: ten new delivery tests and 21 unchanged dependency-patch tests.
They reconstruct the locked CVA6 commit in a disposable archive directory,
apply the existing registered bundle and then the reviewed retirement fix.
The resulting CPU bytes equal the tested SoC overlay. All earlier patch
blocks remain byte-identical; the canonical successor bundle SHA256 is
`4afb780061813ca90b19e94aa6b552ac0c11df7ac57a33bf594a9392468dd3b8`.
Tests cover clean application, idempotent admission and rejection of incorrect
base revisions, unrelated deltas and a noncanonical concatenated patch.

The registry and shared dependency checkout remain unchanged at this checkpoint.
Formal registration waits for the original PV SoC regression. These checks
prove reproducible patch delivery, not the pending architectural result.

## Runtime Selection Preparation

The new experimental `admission.h` and `dispatch.h` use the existing SDK plan,
descriptor and device types. Zeroed options preserve the original native
selection. Shared execution requires explicit validated availability and
platform/context ownership, F16 Decode head rows for exactly one query token,
D64/D96/D128, VLEN1024, RNE and zero vstart. Prefill, segmented D256, active
score features and refill overlap remain on their original routes. No new
capability is advertised, no CSR is modified, and no failure after execution
starts permits a replay through another path.

`stage3_resident_policy_host_20261110_01/report.json` records optimized Clang
and Clang UBSan passes. Each independently checks 1,618 tile maps and 4,051
head pairs, including rows1..8, tile lengths1..64, 64/64/9 context tiling,
odd-head tails, local query-base reset between groups, rejected inputs and
unchanged output on failed mapping. Control-word expectations are constructed
independently from the ABI bit layout. Device availability is deliberately
injected for host tests, not discovered from current production capability.

These are preflight/mapping helpers, not an Attention executor or an integrated
GGML path. No production native source, build wiring, or sealed assembly was
changed. A measured complete-call retention decision and applicable runtime
integration are still required by gate F.
