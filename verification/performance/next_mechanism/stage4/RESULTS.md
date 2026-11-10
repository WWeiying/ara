# Stage4 Evidence And Disposition Ledger

Status: COMPLETE within the finite Stage4 contract. All three RTL jobs and
independent terminal reviews pass. Measured complete SDK speedups are1.02014x
and1.04005x, both below the promotion screen. No model-level gain is claimed.
Final contract: `hardware/docs/INFERENCE_STAGE4_DELIVERY_20261110.md`.
Delivery tag: `stage4-supporting-reuse-20261110`. Preparation/launch descriptions
below record earlier milestones; terminal sections give their final status.

Baseline is `d3d92ad72a3cabb91e8c333186160ae422f0866b`, tagged
`stage3-resident-attention-20261110`. The plan was committed at `ebf9549ed`;
current detailed contracts are in
`hardware/docs/INFERENCE_STAGE4_SUPPORTING_REUSE_20261110.md`.
All receipt paths below are relative to the sole signoff worktree's
`verification/out/` directory. Do not count old Stage2/3 or October software
gains as new Stage4 results.

## A: Retained-Maxima M4 Preflight

Implementation and directed tests are committed at `4018b98a3`. The shared
helper is `software/qbs/experimental/m4_preflight/m4_preflight.h`, SHA256
`71b07f59aa44bea1102674d68fbe9fbaa36fa055f078804b4ff5dd0353fe0291`.
Existing SDK/GGML producers are unchanged. It depends on the actual accepted
parallel-sums producer from llama `da56aa750559c180d631b466de983ff2bb5d54d9`,
not the older SDK packed helper without parallel sums.

`stage4_m4_preflight_20261110_04/result.json` is PASS, SHA256
`8fbd4a5c5cfde66822474b7a4c4555ec4e3b182834331cbc7cf33351707d3aea`.
The separate freeze inventory identifies all nine live/frozen helper inputs.
Independent review found no material blocker and verified 1,441 source pins.

| Scope | Executed checks |
|---|---|
| Host contracts | Eight tests, four non-RVV fallback calls, nine accepted-cache storage checks |
| GNU object | Four audited integer-only preflight bodies; target compilation/linking |
| Spike | VLEN128/256/512/1024; each 323 complete byte/CSR/guard comparisons and 178 metadata checks |
| Real-input controls | Each VLEN crosses 32 FFLAGS and eight VCSR seeds on the captured input; these are not 256 distinct tensors |

The total is 1,292 complete comparisons and 712 metadata checks. This is
differential producer correctness against the accepted baseline, not independent
quantizer accuracy, QBS execution, RTL performance or GGML graph acceptance.
Generated invalid-domain cases use FCSR17; the integer-only object audit is
supplemental evidence, not a claim of exhaustive invalid-input exception flags.

Attempts01/02/03 remain preserved: external-header warning classification,
an invalid assumption that an inlined helper retained a standalone symbol, and
an unsupported installed-Spike command argument. The helper did not change,
no numerical failure was observed, and the final checker was not relaxed.

### Complete-Call Firmware

`stage4_projection_chain_build_20261110_02/build.json` is BUILT_NOT_EXECUTED.
Eighteen host checks pass; source-pin and complete artifact inventories match.
ELF SHA256:
`328a4b93e6f9847d756b8178688534d8a3a494a7fac4491feedceb7fda6db34c`.
Source-pin SHA256:
`66c16cd2d87c6703eb2b8808c3299935f42c8840fcc1d6e6bcdbe27f89032580`.
BUILD01's tool-path resolution failure is unchanged.

The equal-work ABBA uses real Qwen2.5 K1536/M4, full Q/V/K widths1536/256/256.
Both arms retain packed preparation, parallel sums and exact-byte cache reuse:
one cold producer and two hits per chain, 64 native commands and 8192 outputs.
This is a production-helper complete SDK chain, not GGML graph/model timing.
The future runner must inspect retired producer/native entry PCs, all work,
raw results/flags/guards, independent protocol and post-run identities before
any performance result is accepted.

The successor runner passes 14 host checks and two independent operational
reviews. `stage4_projection_chain_vcs_20261110_01` is prepared with 2420 pins
and an exact 40-file execution inventory. Reviewed source-pin SHA256 is
`67275e21f746955638b5e5e5d2bffa2beb075b782bd939291bae8c3c7118a234`.
The directly owned service
`stage4-projection-chain-stage4_projection_chain_vcs_20261110_01.service`
was started; worker PID3954339 reports SIMULATION and simulator PID3954418
was observed with the accepted image and BUILD02 ELF. This is launch evidence,
not a passing numerical or performance result. The run is bounded to9000s,
with no FSDB or automatic retry. Inherited helper and documentation pins
remain sealed while the consumer executes.

### Complete-Call Result And Decision

`stage4_projection_chain_vcs_20261110_01/result.json` is PASS, SHA256
`4169c03338a2c76dddd111085ded3dcdffcb7722b3ce6e886cc4d4e33901eb5c`.
Simulation took2451.73s. Parent verified all2420 input pins and68 artifacts
still match. All32768 outputs, prepared bytes, guards and CSR controls pass;
retired entries are2 baseline producers,2 candidate producers and256 native
commands. The independent protocol and post-image checks also pass.

| Mean cycles | Accepted parallel/cache | Retained-maxima preflight |
|---|---:|---:|
| Preparation/cache handling | 66457 | 56673.5 |
| Admission | 5917 | 5610 |
| Execution | 469669.5 | 469119 |
| Complete SDK chain | 542821 | 532106 |

Preparation/cache handling is1.172629x faster (14.72155% fewer cycles); the
complete chain is1.020137x faster (1.973947% fewer cycles). Hardware native-busy
means remain444400.5/444400 cycles. This software preparation change does not
accelerate that dominant execution work. ABBA complete totals are543893,
532433,531779,541749 cycles; all calls preserve FCSR17,VCSR5,VSTART0.

Disposition: keep the correct helper and reproducible experiment, but do not
promote it into the GGML performance selection/defaults: the complete-call
gain is below the approximately5% screen. No conditional GGML integration is
required for this rejected promotion. Do not repeat/tune this experiment merely
to cross the threshold, or report the preparation ratio as a model speedup.

Independent final review reconstructed all32768 FP32 outputs from the raw
source4 VRF writes, checked the equal-work command/commit stream, and confirmed
39664 matched protocol requests/responses with zero exceptions, errors or
outstanding work. All2420 input pins,1437 firmware-build artifacts,68 run
artifacts and52 image files match. The reviewer agrees with the performance
promotion rejection and the absence of a conditional GGML integration task.

## B: Feature-Bearing Resident Decode

The versioned experimental entry extends only feature-bearing F16 Decode.
Stage3's plain entry, public native selection, arithmetic leaves and capability
remain unchanged. The new feature descriptor snapshots include the inline
per-head arrays; caller slicing remains group-local and positions absolute.

`stage4_resident_features_host_20261110_06/result.json` reports
HOST_GNU_SPIKE_GUARD_PASS_NO_ATTENTION, SHA256
`221c3d05a86f9a143a426bce0f494c3ebe1c833aa909c3e8061406dd6c47af0b`.
Its 18 checks include optimized/UBSan policy/leaf-stub tests, 15,360 maps,
76,800 leaf calls and 32 feature combinations per host configuration. Default/
OFF whole objects and Stage3-enabled/new-feature-OFF whole objects match the
pinned predecessor byte for byte. Host leaf calls are not arithmetic execution.

A bounded Spike guard executes the actual native object with requested1/0,
valid options and deliberately poisoned non-NULL argument pointers. Actual
entry VSTART1 returns status2 before snapshots or inner calls, leaves VSTART1
unchanged, then the assembly caller clears it. The 148-instruction trace has
no inner calls, custom or vector instructions. This is entry-rejection evidence,
not native Attention or target-libm validation. Host05 remains a separate
passing predecessor with a weaker guard; it is not relabeled as failed or used
to claim the corrected guard.

Current native-core SHA256:
`69832cfc9bfcc20aa17b6c57085041fc03ceae77020dd4bc81901590c10d1dfd`.
Source-pin SHA256:
`5c3d8f3c95f3313a14f6da91b7e6d53cac1f3bfc119531402c361698d084fee6`.
Independent implementation review now closes with all five sources, 209 pins
and 260 artifacts matching. Target-library evidence, actual numeric SDK cases
and the paired RTL comparison remain required. In particular, Arm A must bind the
accepted rotating-PV implementation; the pairing environment switch alone does
not establish that strong baseline.

### Target-Library Oracle Checkpoint

`stage4_resident_features_target_20261110_02/result.json` is
`ORACLE_PROBES_PASS_FIRMWARE_PENDING`: 9 explicitly identified case definitions,
27 GNU-newlib libm samples, 7 executed scalar-transform checks and 11 host
checker tests. Parent and independent review verified176 pins,150 artifacts
and all6 source files. Samples SHA256 is
`b778db430da0579430716f318ceb6759d6f73a35a3a901a334df1fcadd095112`;
source-pin SHA256 is
`f41ad4dda44ec1419af00f31ed8a069298b63462a2125c7d84d975b1ebb17889`.
This checkpoint has not executed native Attention or measured performance.
The later firmware must use the same pinned target libm and keep query
conversion outside the ROI, as specified in its build contract.

Attempt01 remains FAIL: a conservative error interval could not prove an
exact F32 halfway reduction. Its positive common-grid integer sum occupies
only27 bits, so every F64 reduction tree is exact. Attempt02 uses zero error
only under the proven <=53-bit exactness condition and retains the previous
bound otherwise. The tie regression checks0x403771ba and NX from clear flags.
Both probe ELFs, requests and complete Spike traces are byte-identical across
attempts; no target arithmetic, inputs or tolerance changed. CSR restore uses
an early-clobber output constraint and is checked in disassembly and at runtime.

## Complete Attention Firmware And Prepared Runs

Frozen firmware, checker and runner sources are committed at `11baa67c7`.
Performance build `stage4_features_full_call_build_perf_20261110_02` has4 calls,
1024 output words,482 legacy and12 resident commands. Functional build
`stage4_features_full_call_build_functional_20261110_01` has18 calls,2816 output
words,713 legacy and30 resident commands, including same-FRM1 fallback.
Each build passes14 host checks; independent review verifies410 pins and202
artifacts, exact SDK/common/wrapper sources, GNU libm and actual ELF bindings.
The first performance build's symbol-name validation failure is preserved;
the corrected binding names the existing hidden resident PV-preparation symbol.

Prepared outputs `stage4_resident_features_vcs_perf_20261110_01` and
`stage4_resident_features_vcs_functional_20261110_01` each pass20 runner host
checks. Independent review verifies1170 pins and43 frozen files per output.
Reviewed pin hashes are respectively
`6393f55986b8cabcde5912d83cb945e540050905cee2df6fb08da60b5850be1b` and
`96f1b4627e623a0f73e25c002a3a9d55688c7030af8ef1e818ede7137c06f37d`.
Direct service launch has been requested. These are preparation/launch
milestones only; numerical, protocol and performance execution remains pending.

### Attention Performance Result

`stage4_resident_features_vcs_perf_20261110_01/result.json` is PASS, SHA256
`9106e86de6b11d91c45900884ae378e956741fe9d99eab19f60e92cb1c505db8`.
Parent verified all1170 pins and71 artifacts. Simulation took1392.71s;
complete worker time was1490.73s including checking. All1024 outputs match
the independent target-libm/ordered oracle; FCSR is3/11/3/11,VCSR5,VSTART0.
Retired entries prove three actual rotating-PV bodies per baseline call,
three resident QK/PV/PV_PREP entries per candidate call and no cross-route
execution. Legacy commands are237/4/4/237, with12 resident commands total.
Independent protocol and post-run image/input checks pass.

ABBA complete-call cycles including normalization/drain are67682,65086,
65218,67841. Strong baseline mean67761.5 versus candidate65152 gives1.040052x
speedup and3.851007% fewer cycles. Each final drain is46cycles. This is the
captured D128/H2/T137 tensor with explicit derived score controls, not a new
captured model behavior or end-to-end speedup.

The result does not meet the approximately5% performance-promotion screen.
Do not default-enable or weaken the baseline to increase the measured ratio.
The experimental feature-bearing capability's final disposition additionally
requires the functional boundary/fallback run and independent terminal review.

### Attention Functional Result

`stage4_resident_features_vcs_functional_20261110_01/result.json` is PASS,
SHA256 `ae0cb8b50bda4a788df05113633186613be6fcdd03c7c11e5d39d173977b2903`.
Parent verified1170 pins and71 artifacts, with no drift. Simulation took
3277.35s; the complete worker took3446.37s. All18 calls and2816 output words
pass, including the same-FRM1 fallback pair. Work is713 legacy and30 resident
commands; final input/image, real-entry, numerical and protocol checks pass.

| Derived functional fixture | Requested OFF cycles | Requested ON cycles |
|---|---:|---:|
| D64/T5 softcap and additive masks | 20874 | 22339 |
| T1 fully excluded, no sink | 14821 | 16024 |
| T1 fully excluded, sink | 15871 | 17789 |
| T65 excluded first tile, no sink | 28019 | 29311 |
| T65 excluded first tile, sink | 30468 | 31639 |
| T65 excluded tail, no sink | 38196 | 39136 |
| T65 excluded tail, sink | 38963 | 40467 |
| Two local H3 groups | 36166 | 37913 |
| Same-FRM1 fallback, D64/T5 | 20670 | 20529 |

These are bounded correctness fixtures, not repeated performance experiments.
The small RNE cases are slower with the candidate, so correctness/capability
coverage does not imply speedup on those shapes. The FRM1 pair executes no
resident arithmetic and is not compared to the RNE oracle. It preserves FCSR41
in both arms; all cases preserve VCSR5/VSTART0. No timing-based default selector
or extra tuning experiment is introduced.

Final disposition after independent functional review: retain B as
an explicit default-OFF experimental capability, reject default/GGML performance
promotion. Existing public native selection remains unchanged.

Independent terminal review reconstructs2560 RNE raw VRF values against the
oracle and256 non-RNE values against the same-FRM1 baseline. It confirms20
groups, query bases resetting0,2,0,2, and zero resident entries on both non-RNE
calls. All6057 vector allocations complete;7036 protocol requests/responses
match with zero exceptions, errors or outstanding work. All1170 pins,71 run
artifacts,202 firmware artifacts and52 image files match. The independent
performance review separately reconstructs1024 values, verifies3657 completed
allocations and4004 matched protocol requests/responses, and agrees with the
below-screen decision. No tests or checkers were rerun to manufacture acceptance.

## Screened Or Deferred Work

| Candidate | Disposition and existing evidence |
|---|---|
| Fixed-capacity QBS replay | Defer RTL change; representative complete-call upper bound about0.63%. No context growth or M8 third bank |
| N64 merging | Defer ABI/reservation expansion; prior repeated-boundary savings do not justify assuming SDK overhead halves |
| Long-K continuation | Keep current routes; older measured ROI lost8.885649%, and excludes preparation |
| Quantized Prefill Register-PV | Existing paired whole C-call result gained only0.89056%; real causal active-suffix handling already works. Do not repeat that experiment or count it as new |
| General active masks | Nonmonotonic-prefix extension alone saves no work on the actual monotonic causal path; no new code/test was added |
| Direct M8 producer | Defer because row-wise M8 and fused-bias M4 tie/rounding contracts differ; no silent arithmetic substitution |
| Multi-query F16 Prefill | No new resident admission: B requires one Decode query token and interprets rows as heads. Existing Prefill/RVV routes remain; no conversion of F32 queries or over-capacity row groups into Decode semantics |
| Quantized KV and causal Prefill | Existing quantized routes and ordered active-suffix handling remain inherited support, not new Stage4 validation or gain; B accepts F16 only |
| Shape and tails | Stage3 D96, GQA and T1 results remain inherited evidence. New B directed derivatives must identify their source, slicing and local-head mapping separately from the captured D128/H2/T137 performance case |

The older Register-PV receipt is
`register-prefill-q4-vcs-20261028-01/result.json`, SHA256
`8a32db0ca352e08fc676b88a640967066b857d3235fe81cc607a57e900f1fac5`.
Its 140922.5/139667.5 mean cycles belong only to that old same-executable pair.

## Stage4 Acceptance Audit

| Requirement | Evidence and status |
|---|---|
| Evidence-backed candidate selection | Closed: all candidate areas have implemented/rejected/deferred dispositions above |
| Correct retained implementations and fallback | Closed: A directed gate, B host06, both B actual SDK runs and independent terminal reviews pass |
| Equal-work complete-call RTL | Closed: three terminal runs pass; strong baselines, actual entry PCs, independent protocol and post-run identities checked |
| Independent feature math | Closed: exact27 target-newlib samples,7 scalar transforms, ordered oracle and actual RTL flags/results; no host-libm substitute |
| Measured promotion decisions | Closed: A promotion rejected; B retained as explicit experimental capability only, default/GGML performance promotion rejected |
| Conditional shared-producer integration | Not triggered: A is not promoted; existing GGML producer/cache/fallback unchanged |
| Pinned delivery and Stage5 boundary | Closed: final delivery contract, source milestone commits, immutable receipts/hashes and delivery tag identify the result |

No required Stage4 work remains after the independent terminal and scope audits.
Actual resident GGML selection and model regression remain Stage5, not a
relabeled SDK timing result.

No Stage4 synthesis, area, timing, power, new bitstream or whole-model result
has been produced. Unrelated dirty files and older acceptance records remain
unchanged.
