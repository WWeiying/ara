# QBS/AKV efficiency execution plan

## Scope

Active objective: complete the prioritized QBS/AKV improvements, not just the
first passing experiment. Preserve ordinary RVV and llama.cpp fallback,
numerical contracts, fault recovery and existing model/shape support. No
synthesis or physical implementation is part of this stage.

Main baseline: `03743c61`. The initial candidate was developed in
`ara_dsa_qbs_activation_overlap`; accepted changes and continuing verification
now belong to `ara_dsa_signoff_integration`. Main's unrelated uncommitted
files and FPGA copies are not experimental outputs. Record each accepted
mechanism in a separate commit; integrate only reviewed, tested changes.

## Current decisions

The detailed ledger below includes earlier experiment states. The current
decisions are:

| Path | Current evidence | Decision |
| --- | --- | --- |
| Shared Q8_0 preparation/packing | Complete matched projection 226244 to 211906 cycles, 6.3374% reduction | Retain capability/shape selection and fallback; not a model-level claim |
| Shared Q8_K M4 preparation | Same-ELF complete projection ABBA 1219006 to 1076923 summed cycles, 1.131934x; live GGML graph gate passed | Retain explicit opt-in; see `qbs_q8k_preparation.md` and Q8_K receipts |
| REFILL/older-RVV overlap | Fixed-address whole Attention ABBA is about 1.55% slower despite the focused overlap opportunity | Keep software scheduling OFF; see `akv_refill_overlap_implementation.md` |
| Long-K VRF continuation | Real M4/N64/K8960 matrix ABBA passes numerically but is 8.885649% slower | Keep experimental QBACC OFF; see `qbs_vrf_continuation_design.md` |
| One-query GQA6 QK PANEL4 | Eight-pair/sixteen-run focused RTL score gate passes; dependent complete Attention ABBA is running | No complete-operator performance acceptance yet; see `../../verification/akv/qk_panel4_rtl_workflow.md` |
| Generic paired-head QK/PV | Focused RTL and complete derived-GQA2 Attention ABBA pass; 161778 to 116768 summed cycles, 1.385465x versus generic AKV | Ordinary RVV comparison and production selection remain open; see `akv_paired_head_efficiency.md` |

The next static candidate is reuse across heads in generic Decode. Current
`akv_v2_compute_scores_f16_generic` loops over heads outside dimensions, so
H heads issue H*D column commands per token tile. The generic PV helper also
reloads each V row per head. For H=2/D128/T64 this is 256 columns and 128 V-row
commands. Pairing heads and using four-column delivery could reduce those
counts to 32 and 64 respectively without reducing arithmetic work or changing
the accumulation order within any output. The isolated implementation is in
`software/akv/experimental/paired_heads/`; its accepted focused receipt is
`verification/akv/results/paired-heads-rtl-20261024.json`. QK uses an independent
finite-input scalar FMA oracle; PV is an exact regression against canonical
assembly, not an independent FP16 oracle. Production selection is unchanged.
The complete derived-GQA2 Attention result is archived in
`verification/akv/results/paired-heads-attention-20261024.json`; this comparison
is separate from ordinary RVV and deployment acceptance. Preserve the specialized GQA6 path and
odd-head fallback; actual odd-head runtime acceptance remains open. Do not edit
sources sealed by active gates.

Local Qwen3 Prefill tensor metadata has 16 Query heads and 8 KV heads (GQA2),
but that capture is Prefill, not a genuine Decode measurement. Its presence
does not prove a Decode model-level benefit. Any successor needs actual
mode/shape selection, unchanged output/flag checks and complete-operator timing.

## Milestones and acceptance

| Priority | Work | Evidence required | State |
|---|---|---|---|
| 1 | Short-block QBS conversion/scale/accumulation throughput | Current-image cycle probes; real Q8_0 and neighboring format inputs; bit/fflags checks; paired cycles and traffic; multi-profile fault regression | Command-level and focused SoC integration passed; no model/PPA claim |
| 2 | QBS activation overlap and Prefill scheduling | Existing M1/M4 overlap plus M5..8 comparison; include activation preparation and traffic; shared runtime selection if software changes | Direct M1..4 overlap validated; remaining scope open |
| 3 | AKV fill/replay/RVV compute overlap | Lifecycle and single-port conflict analysis; real Attention tile; matched QK/PV/numerical checks; shape and fault regression | Restricted SoC REFILL/FMA gate passed; shared runtime Attention pair pending |
| Parallel resource work | Shared QBS/AKV reader; unified legacy/v2 AKV storage | Ownership/drain invariants; unchanged outstanding capacity and context lifetime; matched latency/fault tests | Pending |
| Subsequent coverage work | Quantized KV | One common llama.cpp format first; explicit decode/view contract; native RTL and model numerical validation; F16 fallback preserved | Pending |

Do not represent lower traffic as lower cycles or SRAM capacity reduction as
measured area reduction. Do not replace the requested mechanisms with smaller
test-only variants. A rejected candidate needs evidence and an explicit next
design decision, not a claim that the milestone is complete.

## Stage 1 hypotheses

The historical Q8_0 slot-stall counts are not current performance evidence.
The current FP accumulator has sixteen fixed slots and one issued FP micro-op
per cycle. Its I2F, scale multiply and accumulation form a per-entry chain.

Distinguish these hypotheses with one instrumented command-level image:

1. Arithmetic issue capacity is saturated: valid eligible work and FP fire
   remain high while upstream results wait. More buffering alone cannot help.
2. Fixed result-stream slot binding stalls with other slots free: observe
   requested slot busy, occupancy below sixteen and no accumulator conflict.
3. Selection causes avoidable head-of-line blocking: selected FP unit not
   ready while another operation class could issue.
4. Dependency latency dominates with few eligible entries: no-ready-work
   intervals coincide with in-flight conversions/multiply/accumulate.

Record command-relative cycle, K block, requested slot/accumulator, occupancy,
ready/valid, selected operation/state, FP issue and completion tags, and
upstream result blockage. Bound detailed trace output. Preserve result order
within each output and all rounding/exception semantics.

## Evidence ledger

The previously completed activation-overlap work is recorded in
`qbs_activation_overlap.md`. Its paired and final replay evidence lives at:

`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/qbs-activation-overlap-20261022/`

`final_replay/status.json` is passed, with eight exact result/counter replay
groups and source hashes verified on 2026-10-22. It does not close stages 1,
3, resource sharing, quantized KV, or full-SoC/model integration.

Stage 1 command-level results and invariants are recorded in
`qbs_fp_split_issue.md`. Evidence under `qbs-shortblock-20261022/` contains
81 passing paired command cases without cycle regression and a separate
live-reset/intermediate-result/per-cycle-flags equivalence test. Q8_0 M4 and
M8 command cycles decrease by about 34.4%; this is not a model-level claim.
Focused SoC integration, including resolution of a stale version-1 descriptor
ELF, is recorded in `verification/qbs/SOC_INTEGRATION_20261023.md`.

## Next design gates

Do not infer Prefill efficiency from reduced bytes alone. Analyze shape-aware
tiling alongside the runtime split-K limit: current R4 split-K commands reduce
N to four, introducing a distinct large-K overhead. A layout/address-step
proposal must preserve per-output numerical order and fault boundaries.

For AKV, distinguish overlapped RVV computation on already replayed data from
true concurrent next-tile fill/current-tile replay. Bank ownership, single-port
conflicts and command completion must be proved before introducing concurrency.
Activation preparation and quantized-KV work remain part of the objective;
the short-block improvement does not replace these later milestones.

The cross-N reuse stage is recorded in `qbs_activation_tile_context.md`.
The 4672-byte multirow/Q8_0 extension has progressed beyond its initial
198-case SRAM primitive gate: descriptor/runtime/reference integration,
engine fault/replay checks, capability-aware native QEMU and actual GGML graph
tests have passed. The complete real M4/N896/K896 projection saves 102816
logical read bytes but changes cycles from 256975 to 257184 under the current
low-wait SoC model; it is not a measured latency gain. Oversized long-K matrices
still need bounded residency and partial-output lifetime. New-capability Spike
and production/model performance gates must not be inferred from QEMU results.

Preparation is therefore the current first execution priority. A private VLA
packer reduces the same complete projection from 256975 to 210923 cycles
without changing its output. The separate fused GGML Q8_0 M4 candidate passes
6840 native numerical/environment checks and the real RTL ABBA preparation
gate: 416467 generic versus 278230 vector cycles (two calls per path).
Neither result is a whole-model speedup. Shared public runtime packing passed
43008 layout and 32 invalid-input native checks. Current-runtime forced-scalar
and RVV full-projection twins completed on the unchanged image. Independent
raw-log and provenance reaudit accepts 226244 scalar versus 211906 vector
cycles, a 6.3374% reduction for the matched current-runtime pair. Packing
falls from 31720 to 17388 cycles; quantization is 26062/26067 and matrix
execution 168462/168451. All 3584 outputs pass the independent oracle and
both output checksums match. This is not the larger improvement measured
against the older private-runtime baseline. Original outer worker FAIL
records are retained: the wrapper incorrectly expected `PASS` instead of the
child's `passed`. The successor `audit_runtime_pack_twins.py` accepts only
that exact failure, verifies pins and independently checks both raw results;
its receipt is `verification/qbs/results/runtime-pack-projection-twins-20261023.json`.
The successor `audit_runtime_pack_twins_v2.py` additionally binds the child
simulator files to the parent's pinned image and compares the saved result hash
and parsed projection with the independent raw-log audit. Its mutation tests
pass and `runtime-pack-projection-twins-v2-20261023.json` confirms the same
226244/211906 cycles. The earlier receipt is retained, not overwritten.

The canonical fused GGML Q8_0 M4 helper is integrated behind an explicit
opt-in, still disabled by default. Strict offline audit accepts 6840 native
helper byte/CSR checks and 384 actual GGML graphs at the recorded VLENs and
configuration matrix. The archived receipt is
`verification/qbs/results/m4-production-native-20261023.json`.
The production marker checker requires exact markers, not prefix matching.
Native helper CSR checks use a separate translation unit. A subsequent direct
production repack translation-unit test passed 9120 comparisons across VLEN128
and VLEN1024 (4560 each), covering packed bytes, FCSR and VCSR with matching
result digests. Its pinned logs and status are in
`verification/out/qbs-m4-production-csr-20261023-01/`. This closes that
production-TU functional gate for the pinned build, not arbitrary compiler
options or model-level performance. Q8_K fused preparation remains open:
the Q8_0 preparation result must not be generalized to K-quant model weights.

The canonical Q8_0 helper RTL preparation gate completed with private build and output
under matching `verification/out/qbs-m4-canonical-soc-*` directories. It
reuses the same real input, Linux-generated golden and ABBA harness, replacing
only the candidate include/namespace with the production helper. The builder
rejects unrelated source drift and requires the current generic function body
to equal the archived oracle exactly. Its three unit checks pass. Independent
audit accepts 416387 generic versus 277825 vector cycles across the two calls
per path: 1.4987x preparation speedup. All 3808 output bytes match; requests and
responses both total 2248, with zero exceptions and protocol errors. The
receipt is `verification/qbs/results/ggml-m4-canonical-soc-20261023.json`.
This measures preparation only, not full projection or model execution.
The Q8_K isolated candidate and its distinct numerical contract are documented
in `qbs_q8k_preparation.md`; its production and RTL performance gates remain open.
Its sealed native build includes six real activation captures, 50 datasets,
five rounding modes, eight initial status settings and AVL caps 1/7/16.
The independent worker `run_q8k_m4_native.py` requires 6000 comparisons per
VLEN and identical cross-VLEN result digests. Both boots completed PASS, for
12000 comparisons (1872 candidate and 10128 fallback). Independent raw-log
rechecking accepts the case records and matching per-case digests. Evidence is
archived in `verification/qbs/results/q8k-m4-native-20261023.json`. This is an
isolated-candidate numerical gate, not production selection or RTL performance.

The original scalar-preflight Q8_K candidate subsequently passed its first
independently audited RTL preparation measurement: generic 534591 versus
candidate 495919 cycles across the ABBA observations, 1.07798x (7.234% fewer
preparation cycles). The receipt is `q8k-prepare-soc-20261023.json` in the same
results directory. The full projection measurement remains separate. Existing
retirement traces locate about 34% of the first candidate interval in scalar
domain checking. An integer VLA successor now passes both its isolated
classification gate (24120 comparisons) and the unchanged full quantizer gate
(12000 comparisons), including FP/vector status. Its independently audited RTL
preparation result is 534023 generic versus 391717 candidate cycles, 1.36329x.
The original and successor full-projection runs remain separate pending gates;
no production or model-level successor speedup is claimed.

The independent AKV refill-overlap probe completed PASS under
`akv-refill-overlap-probe-20261023-01.service`. Its exact work/traffic and
architectural-order-to-uop joins were reaudited in
`verification/akv/results/refill-overlap-baseline-20261023.json`. The immediate
case exposes 78 cycles of remaining old arithmetic; the nominal serial case
still exposes 47 because WAIT_IDLE blocks backend issue, not frontend
presentation. Both take 756 joint cycles on the unchanged image. This is an
admission opportunity, not an implemented speedup. Pending older instructions,
all-PE completion and deferred precise fault response must be covered before
relaxing the dispatcher barrier. Matrix partial sums,
Attention intermediate reuse, quantized KV and justified resource sharing
remain open parts of the full objective.

The restricted AKV admission candidate is now connected in the verification
RTL. The actual-sequencer fixture passes 38 checks covering six success/fault
terminal orders and delayed nonzero-lane completion. An independently built
SoC image passed the unchanged sealed REFILL probe. Independently joined
start/first-payload-AR/terminal records prove 41 cycles of accepted-read/older-FMA
overlap; the joint window decreases from 756 to 707 cycles, while the serial
control stays at 756. This is not a full Attention speedup. The receipt is
`verification/akv/results/refill-integration-20261023.json`.
The production PV schedule has a shared,
default-disabled candidate that moves next-tile REFILL before accumulator
stores only for disjoint D128/GQA6 Decode. Host tests and original-entry opcode
equivalence pass; real Attention numerical/performance acceptance and recovery
remain open. Current read faults invalidate AKV context, so transparent
instruction-only REFILL retry must not be inferred from precise response order.
The paired real-capture Attention worker is running under
`akv-refill-attention-pair-20261023-01.service`, using D128, twelve Query heads,
two KV heads and an active KV prefix of 128. Its output is
`verification/out/akv-refill-attention-pair-20261023-01/`. Baseline and candidate
share the accepted new RTL image; only software scheduling differs. The worker
checks the complete 1536-output call, exact paired hash/CSR status and 774
successful AKV commands, with each simulation bounded to three hours.

That real Attention pair has completed functional PASS but does not pass the
performance gate: 106641 baseline versus 108664 candidate cycles. The separate
ELFs place K/V at different page offsets, exactly explaining 32 additional
candidate AXI bursts, but not proving the entire slowdown's cause. The shared
schedule remains disabled. The next discriminating run uses one fixed-address
ELF with both full runtime TUs and ABBA selection; its design and evidence are
recorded in `akv_refill_overlap_implementation.md`. No default enablement is
based on the earlier small probe's gain.

Q8_K private full-production-TU numerical checks and actual GGML graph
OFF/ON selection have passed. The receipts are
`verification/qbs/results/q8k-production-candidate-native-20261023.json` and
`verification/qbs/results/q8k-production-graphs-20261023.json`. These establish
the private candidate's functional integration, not a change to the source
pinned by ongoing projection workers or a model-level performance result.
