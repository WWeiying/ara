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
| Original CPU dirty-state cause | `resident_pv_commit_dirty_20261110_03/report.json` | 72 WT/WB checks; original 23 dirty-state failures versus zero after the patch; other outputs equal. Original PV SoC replay closes through the separate audit below. |
| Original PV SoC boundary | `stage3_pv_boundary_audit_20261110_01/report.json` | Separate audit PASS: unchanged numerical/CSR/VRF/protocol checks; original worker FAIL preserved; 19 mutation tests and all 706 backend ownership lifetimes checked. |
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

The smoke and ABBA firmware builds are complete:

- `stage3_attention_build_smoke_20261110_01/build.json`
- `stage3_attention_build_abba_20261110_01/build.json`

Both use the frozen real Attention input, D128, two query heads and 137 context
tokens split into 64, 64 and 9. The baseline retains panel-four RVV QK and
rotating-register PV. The candidate replaces both arithmetic leaves while
keeping preparation, online softmax, rescaling, normalization and final drain.
The unchanged oracle requires all output bits, flags and memory guards to match.
The new work checker additionally checks every resident operation, per-lane
accepted/returned FMA count, output byte-enable and architectural write.

`stage3_attention_vcs_smoke_20261110_01/result.json` now passes. Its SHA256 is
`1b5b42543463fae9bc04a1c1b730fc8e0a5e72600a41bcfa4c88cf4fb310f88c`.
The one candidate call takes 29,725 cycles including a 34-cycle final drain;
all 256 output words match the pinned independent golden bit for bit, FCSR is
3, and input/guard checks, actual VRF work, independent protocol and pre/post
source/image checks pass. The four context commands and six resident commands
match the full 64/64/9 work. This single-arm run is not a paired speedup or a
runtime acceptance. Simulation wall time was approximately 477 seconds.

The first ABBA preparation stopped before creating its output or starting a
simulator: `admitted_smoke` compared an in-memory integer-keyed lane dictionary
with its JSON report, whose keys are necessarily strings. A diagnostic replay
finds exactly these six lane-key differences; canonical JSON representation
matches every other field without changing any numerical/work checker.
The successor `full_call/run_v2.py` now handles this representation explicitly
and rejects duplicate JSON keys, non-finite values, changed field types and
changed evidence. Its separate immutable smoke-reader instance retains the old
four-file runner inventory; the new worker pins the original four files plus
the two successor files and keeps the original worker's actual file identity.
Nineteen host checks pass (six successor, eight original runner and five work
checks), and independent review finds no blocking issue. The original smoke
PASS, sealed helpers and archived preparation failure remain unchanged.

Preparation evidence is
`stage3_attention_serialization_successor_20261110_01/preparation-receipt.json`,
SHA256 `bceed9dfeab9e437cd2a1a6f5f97426d17170a39acb791487c6489f3c92c7074`.
The ABBA worker `stage3_attention_vcs_abba_20261110_01` has been launched with
inventory SHA256 `ceadb494a1a4aaf6570263f4e4b15d02af985d45372f10fe52d29dcd3429de2f`.
Its original host loop still runs only the original tests; successor tests are
recorded separately before preparation, not claimed as new worker tests.
ABBA performance is pending; the single-arm smoke does not establish speedup.

## Still Required

1. Preserve the completed PV and QK architectural evidence. PV closes through
   its separate strict audit; the original worker's serial-splitter FAIL remains
   unchanged. QK now passes the original architectural/numerical/protocol suite.
2. Complete the running paired ABBA measurement after the passed smoke and
   architectural boundaries. Report full-call cycles separately from resident
   engine cycles; do not infer model speedup.
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
The separate successor audit now passes at
`stage3_pv_boundary_audit_20261110_01/report.json`, SHA256
`8ed1845fa59bfe227cbd9e17ae49bda58cd68514c4406a92b079e789ef827fa9`.
It reproduces the original splitter error exactly once, checks all 706 global
backend lifetimes including 30 PV-attributed uops, and recomputes the independent
protocol result. All original numerical, architectural, writer, byte-enable
and raw-data checks pass. Nineteen host tests include actual-trace mutations for
live VID reuse, missing/duplicate completion, identity swaps, late writes,
corrupt data and premature final allocation. Original artifacts, source/image
pins and the original FAIL remain unchanged. Gate A closes on this separate
audit plus the original execution, not by relabeling that worker or rerunning it.

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
The worker is now terminal PASS at
`stage3_qk_boundary_v2_20261110_01/report.json`, SHA256
`3d346cfdc56d4a310db5d5b7e55cb66de078d522d76dc751837048526e6ce5fc`.
All 24 successful QK operations, 12 true trap groups, two PV operations and
the QBS/RVV postludes pass numerical, actual masked-write, architectural and
independent protocol checks. There are 34 accelerator requests: ten accelerator
rejections plus two CPU-only FS/VS-Off rejections are accounted without ignored
issues. Pre/post source and image checks match. This is architecture-level
evidence for the tested geometry and boundary matrix, not whole-design signoff
or a performance result.

## CPU Patch Delivery

`stage3_cva6_dirty_delivery_host_20261110_01/report.json` records 31 passing
host checks: ten new delivery tests and 21 unchanged dependency-patch tests.
They reconstruct the locked CVA6 commit in a disposable archive directory,
apply the existing registered bundle and then the reviewed retirement fix.
The resulting CPU bytes equal the tested SoC overlay. All earlier patch
blocks remain byte-identical; the canonical successor bundle SHA256 is
`4afb780061813ca90b19e94aa6b552ac0c11df7ac57a33bf594a9392468dd3b8`.
Tests cover clean application, idempotent admission and rejection of incorrect
base revisions, unrelated deltas and a noncanonical concatenated patch.

After the original PV replay and its independent audit passed, the exact
canonical bundle was registered in `verification/patches/dependencies.json`.
Only the reviewed commit-stage hunk and the CVA6 bundle hash/scope were added;
the earlier patch blocks and all other dependency entries remain unchanged.
`stage3_cva6_dirty_delivery_host_20261110_02/junit.xml` records 31 passing
post-registration tests, including the property `promoted registry validated`.
Reconstruction from the locked dependency archive produces commit-stage bytes
identical to the executed SoC overlay. These tests do not launch EDA tools.

The shared live dependency checkout was deliberately not edited. Existing
simulator snapshots remain immutable; future dependency reconstruction must
use the registered bundle rather than treating an older already-patched
checkout as the new delivery. This registration closes reproducible delivery
of the CPU fix, not the pending QK or complete-Attention acceptance.

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

## Generic SDK PV Leaf Preparation

`software/akv/experimental/resident_attention/pv.S` provides an explicit
scalar-ABI H1/H2 leaf: probability, accumulator, old_scale, T, D and H are passed
in a0..a5. It keeps preparation, the PV instruction and active-head stores in
one assembly function, without a benchmark-global selector or intervening C
call. The included `pv_prepare.S` is byte-identical to the sealed preparation
source (SHA256 `8d039dd90da0b00497429be90483d0ed9f3576c1400f458889e9e8cd380968be`);
only its symbol is mechanically namespaced by preprocessing. This preserves
the existing FP conversion/rescale order and avoids an independently rewritten
numerical preparation routine.

`stage3_pv_leaf_static_20261110_02/freeze-review.json` records 18 passing source,
control-path and GNU object checks, 384 T/D/H paths, and matching source/tool
identities. Independent review checks H1/H2 control encoding, scalar ABI,
clobbers, active-memory footprints and unchanged preparation. The first static
attempt is preserved: its checker expected decimal shift immediate 6 while
GNU objdump prints 0x6; the assembly leaf did not change. These are static
checks, not numerical execution, complete-call acceptance or runtime wiring.
The default SDK build/selection, capability and sealed prior assembly remain
unchanged. Actual SDK executor integration and its RTL regression are pending.
