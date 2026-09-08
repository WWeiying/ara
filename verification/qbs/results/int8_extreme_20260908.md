# QBS signed INT8 extreme regression

Date: 2026-09-08. Baseline RTL: `8fafaf3983e644a7bec1aa32aa0f32ec80fe1525`.
The arithmetic correction is selectively ported from `ara_dsa_timing` commit
`7b041ddaeb3fa8a7d65ffe5bfd0f52456cc565f6`; its surrounding pipeline changes
are not imported. Simulator: VCS `V-2023.12-SP1_Full64`, running on the host.

## Root cause and measured discriminator

Q8_0 decoding accepts signed INT8 bytes, including `-128`. In physical M1,
eight `(-128)*(-128)` products total `131072`, one above the signed 18-bit
maximum. The old dot output truncates this to `-131072`; the later 32-bit
subgroup accumulator cannot recover the lost sign.

The same 448 vectors and testbench were run before and after the RTL change.
For case 432 (Q8_0, M1, one row, both operands all `-128`), the trace samples
operands before the clock edge and the dot register after the edge:

| Observation | Before | After | Reference |
| --- | ---: | ---: | ---: |
| Stream-zero dot, cycles 2/3/4/5, each cycle | -131072 | 131072 | 131072 |
| Complete 32-element group/result dot | -524288 | 524288 | 524288 |
| First FP result bits | `c8016400` | `48016400` | `48016400` |

All four new M1 row-count cases failed before the fix, producing 40 group,
result, and first/repeated FP mismatch reports. The original 432 cases and
the 12 new M2--M4 extreme cases already passed. This distinguishes the final
eight-product width from decoding, operand delivery, or general FP ordering.

The fix sign-extends both quad sums before their final addition and keeps
19 bits through `oct_sum_d`, `stream_sum_d`, `stream_sum_o`, and
`dot_stream_sum`. Product/pair/quad widths, registers' pipeline placement,
valid/mask/metadata timing, scheduler, ISA, and numerical contract are unchanged.

## Regression outcome

| Check | Outcome |
| --- | --- |
| Profile matrix: original 432 plus 16 Q8_0 extreme cases | 448/448 PASS |
| First/repeated block latency of all 444 previously passing cases | Identical before/after |
| End-to-end commands: nine profiles, M1--M8, N/K/layout tails | 33/33 PASS; all command cycles identical |
| Validation, MMU, AXI, PMA atomic faults | 4/4 classes PASS |
| Activation context FILL/REUSE/RELEASE | PASS |
| ABI generation, constructed C reference and associated host checks | PASS |

Two real Qwen2.5-1.5B Q4_K_M Prefill captures additionally retain the complete
reduction dimension while narrowing output rows. Both RTL images consume the
same generated vectors. Results match the canonical QBS reference bit-for-bit;
the generator also checks that reference against the captured GGML output.

| Capture | Profile | M | N | K | Before cycles | After cycles |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `blk_0_attn_q_weight` | Q4_K | 4 | 32 | 1536 | 7200 | 7200 |
| `blk_0_ffn_down_weight` | Q6_K | 8 | 16 | 8960 | 44493 | 44493 |

The phase and payload counters also match exactly. These are command-engine
testbench cycles, not full-model or whole-program cycles. This run does not
re-measure PPA or claim that previous model inputs triggered the extreme bug.
AKV and ordinary RVV RTL are untouched; a new full-SoC regression was not run.

## Reproducibility

Raw logs, independent before/after simulator builds, and generated vectors:
`hardware/qbs_int8_extreme_20260908_aea1aR/`.
The testbench and vector generator in this commit are shared by both images;
only the two production RTL files differ. Each simulation has a 180-second
wall-clock limit. Success was checked from complete PASS records, unique case
IDs and absence of `Error:`/`Fatal:`, not process status alone.

| Artifact under the run directory | SHA-256 |
| --- | --- |
| `qbs_rtl_vectors.txt` | `91efc394dcc16ef8aa82243e658fb1ad6bd67c43303b8b6d09fd9109a80b75fa` |
| `qbs_command_vectors.txt` | `24d9d661893dbdbd13b37ea003cb364dc5fe038f7ab042445dedd25b47ecb885` |
| `q4_m4n32.vectors` | `62290eecfa268c9068399561a2431f80352f3db8c7b24d7b235ae28a0af76e28` |
| `q6_m8n16.vectors` | `602473e51199b7d01dfa203fdf8525f911d15a15d05b9d2658c3f5af0a341d2f` |
| `before/simv` | `c533d2e3f18e31bb4cfafe03ce6534e9ab83ffb1eee8021db9b4fcddab1ff5b3` |
| `after/simv` | `83c89db3bb3a3eac0cb47b192e6b9264cabd3c86a9af1b3fd630bed2fc7331dc` |
| `before_engine/simv` | `9f295d830d87166d5b1e3c7b31007899fafa805604e466dade07f65ea05241ea` |
| `after_engine/simv` | `ecc8d733b1672846217cf9d97e0bdd885463cda737a66f323ac124e328b08a28` |
