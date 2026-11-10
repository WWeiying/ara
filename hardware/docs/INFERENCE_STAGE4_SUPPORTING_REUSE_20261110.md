# Stage 4: Supporting Reuse And Applicable-Shape Coverage

Status: COMPLETE within this finite stage. Projection and feature-bearing
Attention complete-call RTL pairs pass at1.020137x and1.040052x, below the
approximately5% promotion screen. Functional boundaries and independent
terminal reviews pass. Retain experimental implementations, not new GGML
defaults. This is not Stage5 model/runtime acceptance. The design/proposal
sections below preserve the implementation plan; final evidence supersedes
their historical pending/approval wording. Current evidence and dispositions are in
`verification/performance/next_mechanism/stage4/RESULTS.md`.
Delivery: `INFERENCE_STAGE4_DELIVERY_20261110.md`, tag
`stage4-supporting-reuse-20261110`.

Baseline: `d3d92ad72a3cabb91e8c333186160ae422f0866b`, tag
`stage3-resident-attention-20261110`, on `ara_dsa`. Preserve its experimental
defaults, ordinary RVV, QBS/AKV arithmetic contracts and runtime fallback.
No bus changes, automatic SRAM growth, new MAC/FPU arrays, synthesis, power
analysis or new FPGA campaign are authorized. No development worktree is added.

## 1. Finite Stage Contract

The governing five-stage table is in
`INFERENCE_STAGE2_RVV_COOPERATIVE_MATRIX_20261109.md`. This stage selects
supporting improvements by net complete-call benefit and correct fallback.
It is not an obligation to implement every candidate, cover every Cartesian
combination, or enlarge hardware until a performance target is met.

Deliverables are:

1. An evidence-backed disposition for preparation/reuse, fixed-capacity
   replay, N tiling, long K, quantized KV and multi-query/shape/tail handling.
2. Scoped implementation and independent correctness checks for the retained
   candidates below, including unchanged numerical controls and no partial
   fallback retry.
3. Equal-work complete-call RTL comparisons against the strongest applicable
   existing implementation, not an old generic or scalar baseline.
4. Explicit applicability, unsupported controls, source/build/input identities,
   measured retention decisions and milestone commits.

Formal GGML selection for the new resident instruction route, representative
whole-model regression and unified deployment remain Stage5. A proven shared
preparation helper can be connected to its existing GGML producer here without
claiming completion of that later system integration.

## 2. Baseline Findings And Candidate Dispositions

| Candidate | Source/evidence finding | Initial disposition |
|---|---|---|
| M4 preparation | Domain validation computes integer absolute maxima, followed by a second maximum scan and first-match search in signed-max selection | Implement retained-maxima preflight against the already optimized packed/parallel-sums/cache baseline |
| Fixed-capacity replay | Existing next-K activation banks are available for M1/M4, but REUSE/RELEASE use current-K scheduling; measured replay has zero compute overlap | Defer RTL change: representative complete-call upper bound is about 0.63%; retain capacity and DIRECT fallback |
| N64 command merge | Prior SDK residual is mostly once per call; plausible repeated-boundary savings were about 418 cycles per pair | Do not widen the ABI or reservations without a stronger complete-call case |
| Long-K continuation | Prior tested continuation lost 8.885649% despite fewer bytes | Keep current DIRECT/segmented handling; do not re-enable QBACC selection without addressing commit/seed/replay cost |
| Quantized KV | Grouped Prefill already shares V decoding; a causal Register-PV successor was already measured at only 0.89056% complete-call improvement | Defer another implementation/ABBA without a different critical-path hypothesis; retain current grouped Prefill |
| Multi-query/features/tails | Decode heads are not Prefill query tokens; non-NULL score features currently reject resident execution despite unchanged downstream feature handling | Add a versioned feature-bearing F16 Decode contract; retain distinct Prefill arithmetic and existing unsupported paths |
| Direct M8 preparation | Row-wise M8 quantization and M4 fused-bias quantization have different tie/rounding contracts | Defer; do not implement M8 by silently reusing M4 arithmetic |

The replay bound uses the real Qwen3 Q6/M1/K2048 RELEASE observation: 4,040
engine cycles, 160 replay-busy cycles, zero replay/compute overlap and 176
activation-wait-classification cycles. Even eliminating all 176 gives only
176/27,931 = 0.63% of the observed complete call. Replay occupancy and wait
classification overlap other activity and are not additive stall categories.
M8 occupies both activation banks and is not admitted by this proposed overlap.

The previous complete M4 context experiment was 0.0813% slower. The current
4672 B/32-block limits remain: Q8_K M4/K2048 needs 9344 B and still uses DIRECT.
M4/K6144 is not made resident by a scheduler change. These are explicit capacity
limits, not missing software switches.

M4 prepare/packed/parallel-sums/cache already exist. Prepared-cache reuse's
2.047641x preparation-only result is baseline evidence, not a new Stage4 gain.
The real optimized Q/V/K chain spends about 12% in preparation/cache work;
Stage2's row-wise-quantize-plus-pack 81.24% figure cannot represent that GGML
cost. No 20% graph speedup is promised for a partial preparation optimization.

## 3. Candidate A: Retained-Maxima M4 Preflight

### Hypothesis

The optimized M4 producer repeatedly reads the same block to validate the
domain, recover its signed maximum and encode values. An integer-only full
preflight can retain the exact signed maximum, reducing repeated reads and
vector reductions without changing quantization arithmetic.

### Implementation Contract

- Start from the accepted llama packed producer with parallel sums, not the
  older SDK copy without that option. Synchronizing the accepted baseline
  source is not a measured new optimization.
- Track each vector lane's earliest position when its absolute maximum
  strictly increases. After reducing the maximum, reduce the earliest matching
  block-global position, not the first matching lane. Preserve signed bits;
  all-zero blocks select positive zero.
- Validate all four rows/all blocks before any output write or FP arithmetic.
  A late invalid block must take the original generic fallback without prior
  quantization side effects. Preserve domain thresholds and FFLAGS.
- Retain at most 24 blocks per row, K<=6144: 384 bytes of bounded software
  metadata. No heap allocation, hardware SRAM or arithmetic resource is added.
  Larger K and other unsupported conditions use the existing optimized path.
- Preserve scale division, fused encoding, packed stores, parallel sums and
  cache validity/producer identity. Cache hits receive no claimed new benefit.
- Use one shared helper for benchmark and the eventual producer selection;
  do not fork an independent benchmark-only quantizer.

### Tests And Measurement

Directed tests cover opposite-sign equal maxima across vector chunks, signed
zeros, domain thresholds, late invalid data, non-RNE, sticky flags, K bounds,
output guards and existing prepared-cache invalidation. Check every prepared
byte, scale and subgroup sum against the unchanged accepted producer.

The representative graph uses the existing real Qwen2.5 first-four-row Q/V/K
inputs: K1536, full output widths 1536/256/256, Q4_K/Q6_K/Q4_K. Clearly retain
its model identity. Use one worker, wide-M off, existing prepare/packed/parallel
sums/cache on. Target one miss and two hits per graph, 64 native commands and
8192 output values. Prefer actual graph execution if an existing bounded RTL
recipe supports it. Do not add a Linux boot or invented thread-library stubs
just to claim that scope. If actual graph execution is available only in native
QEMU, use it for functional/dispatch checks and measure a separately labeled
production-helper complete SDK chain in VCS. Its cycles exclude GGML graph
allocation/planning and must not be called graph or model cycles. Report
preparation and complete-call cycles separately. Use a bounded larger-K
real-data preparation check when available; do not invent a full-width model
result from a cropped case.

## 4. Candidate B: Feature-Bearing Resident F16 Decode

### Hypothesis And Contract

The native v2 core applies score features and online softmax between QK and PV,
but resident admission currently rejects every non-NULL feature object. Add a
new versioned experimental entry/admission contract; leave the Stage3 plain
entry and its meaning unchanged. Do not falsely assert `plain_scores`.

Retain F16 Q/K/V, D64/D96/D128, one Decode token, local head pairs, tile64,
RNE, zero vstart, trap-safe native memory and whole-call ownership. Validate
features with their existing semantics and retain software scale/transform,
sink initialization, rescaling and normalization. Group-local feature arrays
must be sliced by the owner; absolute query/key positions must not be shifted
by resident query-base selection. Do not skip masked QK/PV arithmetic to change
flags. Failure after execution begins is terminal, not retry/fallback.

The ordinary native fallback and the original experimental entry must remain
unchanged, including unsupported score or refill-overlap cases. Capability
remains zero. No new hardware feature or instruction encoding is required.

### Tests And Measurement

Cover feature combinations, distinct per-head/group parameters, nonzero
positions, window boundaries, fully excluded tiles, sinks, multiple context
tiles and sticky flags. Original plain SDK cases remain regression controls.
Use pinned real inputs, full D and enough context tiles to expose recurrence;
label any derived geometry rather than calling it a newly captured model.

The performance baseline is the existing feature-native explicit paired-head
path with the accepted rotating-PV wrapper explicitly linked and verified in
the ELF; `AKV_PAIR_HEADS=1` alone does not establish that binding. Do not use
auto selection's generic feature fallback. Compare complete calls including
transformations and final drain. Candidate and baseline must match
every output bit and CSR state, supplemented by independent arithmetic and
feature checks. Nontrivial target expf/tanhf behavior needs target evidence;
host libm is not assumed bit-equivalent to the target library.

### Candidate B Owned Implementation Plan

The only existing SDK implementation file in this change is
`software/akv/src/akv_v2_native_riscv.c`. New versioned headers live under
`software/akv/experimental/resident_attention/features_v2/`; new host/GNU tests
live under `verification/performance/next_mechanism/stage4/resident_features/`.
Stage3 `admission.h`, `executor.h`, dispatch and assembly leaves remain unchanged.

`AKV_EXPERIMENTAL_RESIDENT_FEATURES_V2` defaults to zero and requires the
existing `AKV_EXPERIMENTAL_RESIDENT_ATTENTION=1` resource/leaf build opt-in.
Only the new entry receives the new policy. Its versioned options describe
native software score order, one Decode query token and group-local head rows;
they have no `plain_scores` field. After trap-safe platform admission, read
entry CSR eligibility before any potentially vectorized snapshot libc call;
an ineligible entry cannot become resident after a copy clears vstart. Copy
device/options/features, including inline per-head arrays, before entering
the shared core, which rechecks actual CSRs. Check plan alignment before any
descriptor field read and the feature-row count against the group's descriptor,
and use existing feature validation, including absolute key-position overflow.
The caller slices per-head arrays and owns immutable inputs across all groups.
Unknown ABI/policy or inconsistent group metadata is a pre-execution error;
Prefill row meaning is rejected before native execution. A valid Decode call
that misses optional resident eligibility keeps its original explicit/auto
native policy. Both requested and effective refill overlap prevent selection.
No mid-loop route selection, CSR write or post-start fallback is introduced.

The existing software transform, sink initialization and online recurrence are
not edited. Keep the original Stage3 preflight body exactly intact; the new
flag-only preflight repeats its small geometry block to preserve old codegen.
Host gates compare GNU whole objects against archived Stage3 SDK `ca772ef909`
for default and explicit-OFF builds, and also check the old resident-enabled build
with the new feature flag OFF. Host leaf stubs prove routing only, not target
arithmetic. GNU checks inspect the actual enabled native object and build guards.

### Candidate B Capture, Baseline And Oracle Plan

The verified capture is under the signoff output root
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`:

- `e2e_qwen3_f16_attention_capture_20261106_01/capture/decode/block/`
  contains the original model tensors.
- `e2e_qwen3_f16_native_data_20261106_02/` contains the mapped inputs;
  `result.json` SHA256 is
  `0fb5797dfed0d5d6bfaaf1e7b611f110b9b0a625fa1b67977ba86ce7a9e3581a`.
- `decode_query_f16.bin` SHA256 is
  `24bdf29c0111f117fdb3ec460de88b96740e3a26b81e456e4d5be0d7ea4c4b99`.
  The checked geometry is D128, H2, one KV head, one query token, 137 visible
  tokens and capacity256. The captured scale bits are 1035273459.

No D64/T257 capture has been established. The first proposed performance pair
keeps the original D128/H2/T137 Q/K/V and scale. Feature parameters and changed
masks are explicit derived controls, not captured model behavior. Cropped
D64/D96 or tail cases, and any repeated-row longer context, must have a separate
derivation receipt and cannot be called a new captured shape or model gain.

Both arms call `akv_experimental_attention_execute_features_v2_native` with
`automatic=0`: Arm A uses `requested=0`, Arm B uses `requested=1`. The only
enabled environment option is `AKV_PAIR_HEADS=1`, with VLEN1024 and the existing
panel4 capability. That switch selects paired panel4 QK but does NOT select
the accepted rotating PV baseline.
Arm A must additionally link the accepted
`verification/performance/resident_rvv/rotation/pv_rotation.S` wrapper through
`--wrap=akv_experimental_pv_f16_pair`, following the Stage3 strong-control
binding. Require final-ELF call-target/disassembly proof and actual entry evidence
for the rotation body, not merely linked symbols or an environment setting.
Performance bindings are parent-owned and independently audited. Arm B must
bypass the wrapper. Both use the same validated group-local
feature object, masks, layout, tile64, libm, RNE, initial flags and no refill
overlap. Do not use native-auto's generic feature fallback as the performance
baseline, or the Stage3 plain golden as a feature golden. A same-image bounded
ABBA must include entry/admission, FULL/REFILL/RELEASE, software transforms,
preparation, output normalization and final drain. Require per-call legacy
command counts 237 for A and 4 for B, with 6 resident commands for B, plus
actual retired wrapper/entry and useful-work checks. Native target cases and
a runner are deferred until core freeze and independent parent review.

The performance controls use nonzero absolute query/key positions, distinct
per-head linear position slopes and sinks, and a bounded window with excluded
and included positions. Keep `softcap=0` in this pair so a new tanhf cost does
not dominate the comparison. Choose/freeze exact controls only after confirming
they exercise a nonzero alpha-expf argument, without selecting them for speed.
Proposed initial controls for that independent check are key base4096,
query position4232, window left100/right0 (include local tokens36..136),
position slopes `{0x1p-7f, 0x1p-6f}`, sinks `{-2.0f, -1.0f}`, mask scaling
disabled and captured masks unchanged. These are a review proposal, not a
generated/frozen target fixture. Preserve all three QK/PV tiles, including
excluded positions. Separate tiny functional fixtures should exercise softcap
2, an entirely excluded tile with/without sinks, both inclusive window edges,
mask-before-scale versus window-after-scale exceptions and group-local array
slicing/querybase reset. Do not use these small fixtures for performance claims.

Before target-case coding, the oracle contract is: independently reconstruct
ordered QK/PV and scalar feature operations with SoftFloat plus the unchanged
RVV softmax polynomial/reduction order. Model the actual C branches in
`akv_attention_score_transform`, not the header's window-last prose: mask
`0xfc00` returns before dot*scale; otherwise dot*scale executes before window
exclusion, which returns before softcap, position bias and additive mask
scaling. Preserve each branch's flags and do not skip QK/PV work. Derive tile
maxima independently of expf, then collect every required alpha-expf sample
using a bounded target-newlib Spike probe. Small separate functional cases
cover nonzero softcap, sinks and both window boundaries; their tanhf samples
must be probed before deriving the resulting maxima/expf samples. For every
nontrivial target `expf` and `tanhf`, capture input bits, output bits and newly
raised flags using a separately checked scalar harness linked to the identical
pinned GNU target libm. Restore the harness CSR state around each probe;
do not instrument CSR writes into the
measured attention call. Require complete sample coverage and matching target
library/ELF identity; host glibc values are not substitutes. Cover mask early
return, absolute window boundaries, feature-local head indexing and sinks with
independent directed expectations. The mathematical F32 reference is a
tolerance cross-check only. Component/native pair equality alone is insufficient
to claim independent feature arithmetic acceptance.

Reuse only the ordered arithmetic foundation from the Stage3 `flags_v2/`
fixture in a new successor oracle, never edit that sealed fixture or retain
its host-libm assumption for new samples. Initialize sink maximum/sum exactly
as native (sink/1), keep the F64 reduction-to-F32 proof, and attribute alpha
conversion, seed rescale and probability conversions to `PV_PREP`, distinct
from resident PV MAC flags. Pin probe source/compiler/libm/ELF and exact sample
sets before generating expected output/FCSR; reject missing or extra samples.
Probe execution and target-case implementation still need parent approval.

### Candidate B Host Freeze And Attempt History

The five owned implementation/test files are frozen for review after
`stage4_resident_features_host_20261110_05/result.json` reported
`HOST_GNU_PASS_NOT_EXECUTED`: 16 checks, optimized and UBSan runs each covering
15,360 maps / 76,800 leaf-stub calls / 32 feature combinations. Native target
execution, target-libm validation and performance measurement are all false.
The final source-pins inventory matches all live owned sources and archived
inputs. Stage3 sealed helper sources and dirty assembly were not edited.

All attempts remain under the signoff OUT root; no FAIL is relabeled:

| Attempt | Cause | Scoped fix/disposition |
|---|---|---|
| `host_20261110_01` | New C test signed/unsigned comparison rejected by `-Werror` | Test-only unsigned literals; no production change or warning suppression |
| `host_20261110_02` | New public header unnecessarily included sealed dispatch header; C++ `-Werror` exposed its aggregate-init warning | Include only existing admission header; sealed header and warning gate unchanged |
| `host_20261110_03` | Factored native preflight changed Stage3-enabled GNU object, 23216 to23224 bytes; `.text` 11926 to11936; core frame720 to736 with descriptor spill/reload | Restore original Stage3 function exactly; geometry duplication only under new flag. A production codegen/identity regression, not demonstrated numeric failure |
| `host_20261110_04` | All host/GNU, object-identity and entry-CSR gates passed; final Python source-range check had tuple-unpacking typo | Harness-only direct pair assignment, same comparison; production sources unchanged for05 |
| `host_20261110_05` | All16 gates pass | Freeze; no checker relaxation |

The static03 object diff was inspected before04. The new entry also captures
actual vlenb/frm/vstart before its first snapshot/libc call: GNU04/05 show CSR
reads at2bae/2bb2/2bb6 and memcpy relocation at2bc0. This guard affects only the
new API. Optimized/UBSan checks explicitly cover mask-before-scale and
window-after-scale flag behavior, and misaligned-plan rejection before reads.

GNU comparisons archive SDK revision `ca772ef9096899be4749335581eb45077d5377e8`
directly; the only SDK delta to Stage4 baseline is the resident README. Both
default and explicit all-OFF objects have SHA256
`2158b0f23c3683927701c09ecfce56ee1ae5d6f3f55eef8366b88345db7c4d3f`.
Both Stage3-enabled / FEATURES_V2 absent-or-zero objects have SHA256
`490601fcca1ee1566233af3f709967ff7c5675229dcfdea3a5781f570d08313e`.
These are whole-object identity checks, not extracted text comparisons.

Final05 result SHA256:
`0f4d6fdb914e083d61667eb52c7c5af80c6c186ebef2216bdbe1ca9d9994d29e`.
Final05 source-pins SHA256:
`ef65fc5fe3c4ee16d79b57bcd074625a98b5649db39503e2b30da4818454ec5d`.
The inventory includes full hashes for all five owned files; native core is
`c00286e036ccbce817cc3ac0a250ce2373881b9b33713db10c0a722691b68e84`.

Exact completed command from the Ara repository root:

```sh
python3 -B verification/performance/next_mechanism/stage4/resident_features/test_features.py --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage4_resident_features_host_20261110_05
```

This output directory is immutable; any independently authorized reproduction
requires a fresh suffix. `commands.json` retains every compiler/run command and
per-command logs. No target probe, VCS, SoC build, RTL change or commit was run.

### Defensive Entry Follow-Up

The05 checkpoint above is historical. Independent review identified that
capturing a nonzero actual VSTART then disabling only resident selection did
not establish safe fallback through potentially vectorized snapshot libc.
The current new entry returns RUNTIME_UNAVAILABLE immediately after capture,
before copying or calling, and leaves VSTART unchanged. This rejection applies
also when requested=0; valid-ABI optional misses still keep native fallback.
Existing entries and old/new-feature-OFF whole objects remain unchanged.

`stage4_resident_features_host_20261110_06/result.json` passes18 gates. A bounded
Spike guard links the actual native object without numerical stubs, calls both
requested states with deliberately poisoned arguments, observes status2 and
unchanged VSTART1, then clears VSTART in assembly. Its148 instructions contain
no inner calls, custom or vector instructions. This is actual entry-rejection
evidence, not native Attention or target-libm arithmetic acceptance.
Current native C SHA256 is
`69832cfc9bfcc20aa17b6c57085041fc03ceae77020dd4bc81901590c10d1dfd`.
The06 result SHA256 is
`221c3d05a86f9a143a426bce0f494c3ebe1c833aa909c3e8061406dd6c47af0b`;
pins SHA256 is
`5c3d8f3c95f3313a14f6da91b7e6d53cac1f3bfc119531402c361698d084fee6`.
Independent read-only review finds no remaining implementation-review blocker;
target math and paired VCS acceptance are still pending.

## 5. Screened Candidate C: Quantized Prefill Register-PV

Before a new experiment, review
`verification/akv/quantized_kv/register_pv/PREFILL_EXPERIMENT.md` and terminal
receipt `register-prefill-q4-vcs-20261028-01/result.json` (SHA256
`8a32db0ca352e08fc676b88a640967066b857d3235fe81cc607a57e900f1fac5`).
The same materialization-removal idea was already implemented for the actual
causal query-major/GQA-minor row order. Its active suffix excludes finished
rows correctly; 1792 instruction-level cases and a real Qwen3 paired RTL call
passed. Baseline/candidate means were 140922.5/139667.5 cycles, only 0.89056%
improvement. This is old evidence, not a new Stage4 measurement.

A general active-row mask would admit nonmonotonic prefixes, but does not by
itself reduce work on the existing monotonic llama.cpp path. Therefore the
proposed extension below is **deferred**, not an implementation or target-test
requirement for this stage. Do not duplicate that ABBA or add a production
branch for the same marginal result. Reconsider only with a new measured
critical-path hypothesis or a real runtime needing the extra prefix order.

### Hypothesis And Contract

Retain current QBS QK commands and grouping. Decode each Q8_0 V fragment once
into RVV registers and update only the visible rows. An inactive row performs
no arithmetic or output access; multiplying an invalid row by zero is not an
equivalent substitute. Keep each row's token-order FP32 MAC, conditional scale,
sum recurrence, normalization and existing production arithmetic bindings.

An eventual successor would use an explicit active-row mask. Preserve the
current grouped-prefix implementation as the baseline and fallback. Admission
must check real CSR state and existing memory/alias rules before initialization
or callbacks. After work starts, late callback/leaf failure is terminal.
Do not replace quantized QK or FP32 PV with F16 resident math.

Required tests for such a future successor would cover both supported K formats, uneven/nonmonotonic visible
prefixes, row-group boundaries, D fragments/tails, strided K panels, inactive
guards/flags and early rejection versus late failure. The first equal-work
paired VCS experiment uses real captured quantized-KV data and the production
value binding. Include unequal causal prefixes and a tile boundary when the
available capture permits; label derived prefixes explicitly otherwise.

## 6. Execution And Retention

First run independent host/GNU/Spike correctness gates in parallel. Then freeze
the owned sources and obtain review before VCS. Reuse the accepted Stage3 SoC
image only for software-only changes whose exact RTL/configuration matches.
All new outputs are independent directories under the sole signoff worktree.
Use GNU tools and host VCS; no ZCC, Verilator, URG or EDA container for VCS.

Prefer one discriminating ABBA per retained candidate over parameter sweeps.
Keep K and numerical order, crop only bounded output/shape scope where needed,
and account for setup, cache lookup/miss/hit, planning, commands, output and
drain. A single case should fit approximately three hours; larger work needs
an explicit bounded redesign, not an unbounded timeout increase. Long workers
are directly systemd-owned; confirm actual simulation once and inspect the
terminal result without frequent polling.

Approximately 5% complete-call improvement beyond observed variation is the
supporting optimization screen. Below-target/negative results are preserved;
they do not justify default enablement or another blind trial. Feature/shape
coverage improvements must have their numerical and fallback evidence even
when no broad speedup is claimed. Stage2/3 and older software gains are never
added to Stage4 as if newly obtained.

Every candidate receives a final retained/rejected/deferred decision. Final
closure requires scoped source commits, tested applicability/fallback, pinned
evidence and an explicit handoff to Stage5. It does not require new hardware
capacity, a win from every candidate or whole-model/physical/FPGA acceptance.
