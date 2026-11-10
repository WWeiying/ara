# Stage 3 Candidate Delivery Contract

Status: gates A through E are closed within the scopes below. Gate F native SDK
execution is running; this is not yet a completed stage or a board delivery.
The development branch is `ara_dsa`. No physical signoff, new FPGA result or
whole-model speedup is included.

## 1. Delivered Mechanism

Resident QK and PV use the actual RVV lane FPUs, existing AKV Q/K/V stores,
registered payload path and the same lane-private 16 x 64-bit accumulator
array (512 B across four lanes). QK and PV are successive modes, not concurrent
users of a duplicated FPU or accumulator. There is no SRAM capacity increase,
external bus change or new arithmetic array.

QK performs dimension-ordered FP32 FMAs on exactly widened resident F16 Q/K
inputs. PV keeps token-ordered FP16 accumulation and its existing preparation.
Only active elements execute and contribute flags. The central controller
retains ownership through the last acknowledged architectural write, including
uncancellable reads and error drains. Ordinary RVV, QBS and resident arithmetic
cannot overwrite each other's in-flight work.

Software keeps FULL/REFILL/RELEASE, scale/mask, online softmax, cross-tile
rescaling and final normalization. Query-base selection is local to the current
FULL-loaded group. Up to two heads execute per leaf; further heads use local
pairs 0/2/4/6. Long contexts retain software tile64 iteration rather than a
larger resident allocation.

## 2. Version Composition

| Part | Required identity |
|---|---|
| Production RTL archive | `9af19508de139641ea561ccdbd3114eba4007c6e` |
| Accepted SoC build | `verification/out/stage3_soc_20261110_02/build.json` |
| CPU dependency | `b29fd3cf906e7f4c71da4c2f46451c4c60a4487f` with the reviewed retirement overlay |
| Registered dependency patch bundle | `verification/patches/cva6-local-fixes.patch`, SHA256 `4afb780061813ca90b19e94aa6b552ac0c11df7ac57a33bf594a9392468dd3b8` |
| Native SDK executor | `ca772ef9096899be4749335581eb45077d5377e8` |
| SDK functional harness | `cfdc801ba`, corrected sources under `full_call_sdk/flags_v2/` |
| SDK functional ELF | SHA256 `d8c413799646ddf3286347d0c18a76eaaadce27a2840fc3bf4f46f3d7d1de17c` |

All `verification/out` receipt paths in this document are under
`/home/wangwy/openproject/ara_dsa_signoff_integration/`. The build source and
image inventories, not the development worktree's mutable HEAD, identify the
executed design. The shared live dependency checkout was not edited for this
stage. Reconstruct locked dependency inputs with registered patches, or use
the checked build snapshot; do not substitute unchecked local dependency files.

The exact CPU `commit_stage.sv` preimage SHA256 is
`bf59bfa36960ec6227cb49d86e60f8b8f9507590f64ecfafffa9d8d8f94abb60`;
its tested postimage is
`ce293df18df94a81a0e4fe99ebc798a356c437219de79d79f900bf2362f93249`.
The fix marks FP state dirty only for acknowledged, non-dropped,
non-exceptional accelerator FP retirement. Native FP and flag expressions
remain unchanged. The CPU overlay is part of the tested composition, not an
optional performance setting.

The SDK firmware archives `8dc915db8` plus exactly two approved files matching
`ca772ef90`: native v2 C and the experimental executor header. Existing QK/PV
leaves are already in that archive. Its archived `akv_v2_attention_rvv.S` has
SHA256 `0e90dccf193c43bcda367fa18813bedb1077e9790795635f9efa993871a20061`.
The user's uncommitted assembly is excluded from this contract.

## 3. Configuration And Selection

The measured image uses four lanes, VLEN1024, 16 MiB simulation-only L2,
resident QK/PV enabled, capability zero and the real scalar dispatcher.
Shared integer multiplication is enabled; shared-FMA replacement and stage-two
QBS multiplier borrowing are disabled. The latter is a separate candidate,
not a prerequisite or a hidden part of the measured speedup.

Build `akv_v2_native_riscv.c` with
`AKV_EXPERIMENTAL_RESIDENT_ATTENTION=1` and link `qk.S` plus `pv.S` for the
experimental entry. The default macro is zero and existing SDK entries never
choose the new leaves. The default/unset and explicit-zero GNU whole objects
are byte-identical to the pinned predecessor in the checked configuration.

Admission requires explicit experimental availability, eligible native memory,
FS/VS enabled, whole-call ownership, F16 payloads, D64/D96/D128, VLEN1024,
RNE, vstart zero, one Decode query token, normalized plain score features and
no effective refill overlap. Caller capacity and nonaliasing checks precede
the first group. Rejected resident selection retains the original native
explicit/automatic policy; it is not a generic-kernel substitution. After work
starts there is no replay or fallback retry.

Prefill queries, segmented D256, non-F16 data and unsupported score features
retain existing paths. A fitting row count does not establish Decode semantics.
Advertising a capability or enabling a GGML policy requires a later versioned
integration; neither is implied by setting experimental options.

## 4. Acceptance Ledger

| Gate | Authoritative receipt | Accepted scope |
|---|---|---|
| A: original PV | `resident_pv_commit_dirty_20261110_03/report.json`; `stage3_pv_boundary_audit_20261110_01/report.json` | CPU WT/WB cause reproduced/fixed; original PV raw data, CSR, VRF and independent protocol verified by separate audit |
| B: actual shared FPU | `resident_qk_lane_fpu_20261110_01/report.json` | Actual lane FPUs, independent SoftFloat, both multiplier configurations, rounding/specials/tails/ownership/reset |
| C: resident dataflow | `stage3_reader_gate_20261110_01/report.json`; `stage3_control_gate_20261110_03/report.json` | Synchronous storage and masks, backpressure, cancellation and final-write debt; control lanes are explicitly stubs |
| D: architectural QK | `stage3_qk_boundary_v2_20261110_01/report.json`; `stage3_abi_host_closeout_20261110_01/junit.xml` | 24 successful QK operations, 12 actual rejection groups, PV/QBS/RVV coexistence; 17 additional host ABI tests |
| E: complete-call performance | `stage3_attention_vcs_abba_20261110_01/result.json` | One captured real Qwen3 D128/H2/T137 input, optimized baseline, equal work and all output bits/flags/guards/protocol |
| F: actual SDK | `stage3_attention_sdk_vcs_20261110_01/result.json` | Pending: three complete native SDK calls, actual entry PCs, numerical/CSR/work/protocol and post-run identities |

The original PV worker's FAIL is retained. It arose from an invalid global
serialization assumption in the work splitter; the separate audit checks all
706 ownership lifetimes without changing its original receipt. A separate
passing audit is not a relabeled original PASS. Earlier preparation and
testbench failures also remain available.

Host tests do not replace RTL execution. Stub control lanes do not prove FPU
arithmetic, and FPU component checks alone do not prove four-lane composition.
The SoC architectural and complete-call gates provide that integrated evidence
for their stated cases.

## 5. Measured Retention Decision

| ABBA arm | Complete-call cycles, including final drain |
|---|---:|
| Optimized RVV A0 | 35,049 |
| Resident B1 | 28,796 |
| Resident B2 | 28,626 |
| Optimized RVV A3 | 34,341 |
| Baseline mean | 34,695 |
| Resident mean | 28,711 |

The reduction is 5,984 cycles, 17.2474 percent, or **1.20842x** speedup. The
baseline already uses panel4 RVV QK and rotating-register PV. All 1,024 FP32
values across four calls match the independent tile64 golden bitwise; FCSR is
3 in every call. Preparation, online softmax, rescaling, normalization and
final drain remain included. This positive result supports retaining an
explicit experimental candidate, not default deployment or model-wide speedup.

The performance worker's `performance_acceptance=false` remains unchanged:
it is a measurement receipt, not deployment authorization. Gate F's OFF call
is a functional fallback check and is not the optimized performance baseline.
Its diagnostic cycles must not replace this ABBA comparison.

## 6. SDK Closure Still Required

The running SDK worker is pinned by SHA256
`d532da52c58a5742c294cab8a7148397a08e4e2ec13cb1a568e3f7c0582da3c2`.
It must pass all of the following before this stage is marked complete:

1. OFF and ON original D128/H2/T137 plus a distinct derived D96/H6/KV2/T65
   case: all 1,088 outputs exact, FCSR 3/11/3 and memory guards intact.
2. Six actual Decode entries and four experimental group-executor entries,
   bound to the retired ELF instructions rather than software-only labels.
3. Exact legacy and resident command counts, active-lane FMA work, local
   query-base selection, architectural write masks and final completion.
4. Independent protocol PASS with zero exceptions, errors or outstanding work;
   source, image, ELF and checker I/O identities match after execution.
5. Final source/version disposition and explicit fallback/availability rules
   recorded without changing any original receipt or unrelated dirty input.

The D96 case derives distinct rows/groups by raw-bit permutation of real model
data; it is not six independently captured model heads. Four wrong-routing
mutations change every intended affected head. Corrected `PV_PREP` and `PV`
counter scopes distinguish software preparation from hardware FMA flags.

The source and commands are in
`verification/performance/resident_rvv/qk_shared/full_call_sdk/WORKFLOW.md`;
full receipts and scope details are in the adjacent `RESULTS.md`. Stage four
shape/performance expansion, formal GGML selection, model regression, physical
closure and FPGA migration are not silently included in this delivery.
