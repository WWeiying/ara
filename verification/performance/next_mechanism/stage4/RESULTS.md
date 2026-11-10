# Stage4 Evidence And Disposition Ledger

Status: implementation/correctness checkpoints exist; complete-call RTL
evaluation is not yet executed. Stage4 is not complete and no new performance
gain is claimed here.

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
any performance result is accepted. Its VCS runner is being prepared.

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

## Screened Or Deferred Work

| Candidate | Disposition and existing evidence |
|---|---|
| Fixed-capacity QBS replay | Defer RTL change; representative complete-call upper bound about0.63%. No context growth or M8 third bank |
| N64 merging | Defer ABI/reservation expansion; prior repeated-boundary savings do not justify assuming SDK overhead halves |
| Long-K continuation | Keep current routes; older measured ROI lost8.885649%, and excludes preparation |
| Quantized Prefill Register-PV | Existing paired whole C-call result gained only0.89056%; real causal active-suffix handling already works. Do not repeat that experiment or count it as new |
| General active masks | Nonmonotonic-prefix extension alone saves no work on the actual monotonic causal path; no new code/test was added |
| Direct M8 producer | Defer because row-wise M8 and fused-bias M4 tie/rounding contracts differ; no silent arithmetic substitution |

The older Register-PV receipt is
`register-prefill-q4-vcs-20261028-01/result.json`, SHA256
`8a32db0ca352e08fc676b88a640967066b857d3235fe81cc607a57e900f1fac5`.
Its 140922.5/139667.5 mean cycles belong only to that old same-executable pair.

## Remaining Stage4 Acceptance

1. Close independent implementation review and freeze applicable source inputs.
2. Run the bounded paired complete SDK-chain/Attention VCS cases on the accepted
   unchanged SoC image, using directly owned services and independent outputs.
3. For new feature math, check every required target-newlib expf/tanhf sample;
   host glibc is not a target oracle. Preserve actual transform branch/flag order.
4. Give each candidate a measured retained/rejected/deferred decision. Insufficient
   gain is not a reason to weaken the baseline or default-enable a path.
5. Connect any retained shared producer to its existing runtime selection with
   functional evidence, preserve unsupported fallback, and pin source/evidence
   commits for Stage5. Do not claim GGML graph cycles from SDK timing.

No Stage4 synthesis, area, timing, power, new bitstream or whole-model result
has been produced. Unrelated dirty files and older acceptance records remain
unchanged.
