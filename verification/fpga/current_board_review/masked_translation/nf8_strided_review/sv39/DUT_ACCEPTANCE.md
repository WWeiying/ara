# Candidate04 Selected4: Independent Acceptance

Status: **INDEPENDENT_CANDIDATE04_SELECTED4_ACCEPTED**. Four completed CSVs were
replayed read-only through the pinned scalar observer and independent Spike
comparison ledgers, not accepted solely from console PASS or aggregate JSON.
Every replay result exactly matched its saved per-case analysis and the
aggregate. No rerun, RTL/source/ELF change, or NF7 progress query was performed.

## Measured Results

| Original trial | Checks | Last cycle | Last retirement order | Runner seconds | Checkpoint bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 19 | 3122 | 374954 | 282782 | 470.1075 | 66392 |
| 17 | 3122 | 374876 | 282782 | 442.9078 | 66392 |
| 67 | 3166 | 374784 | 283214 | 432.2455 | 66696 |
| 31 | 2984 | 277218 | 212851 | 322.4095 | 33368 |

Total12394 comparisons, seven checkpoints, three precise page faults and four
expected S-mode completion ecalls. All four have zero firsterror/unexpected
state, one completed selected case, full environment restoration,
magic0x6e38737633390004 and CTRL exit0. Scalar array scans cover complete arrays;
the check count is not a substitute for the separately validated byte state.

Trials19/17: cause13, target PC0x80001566, tval0x40001000,
VL8/vtype23/vstart3, fcsr117/vcsr5 and MXR0. Fault checkpoints are at
cycles189231/189254, before PTE repair and prefix poisoning. Same-PC/vstart3
retry completes before the younger marker and final checkpoints. Saved/final
v31[2] are37603/37677 respectively; prefix backing is correctly poisoned to
37560/37750. The physical fractional tails, cap-tail, guards and complete
backing/gaps are included in the observer.

Trial67: cause15 at PC0x800015f4, tval0x40001000, VL8/vtype23/vstart3.
Fault/final checkpoints are cycles190686/373780. Saved and final source
v31[2]=330; completed-prefix backing remains273 after retry. The fault-segment
store oracle accepts independent original/correctly-stored accessible fields,
rejects third values and preserves exact protected/non-target memory. No
segment-atomic or fixed partial-field order was substituted for the oracle.

Trial31: no page fault, no repair/retry; only cause9 completion ecall at
PC0x80001510. Final VL16/vtype23/vstart0. Old v31[2]=0x5b and backing37603 are
unchanged, as are the complete architectural guards/memory/PTE state.
Scalar CSV proves no architectural fault/data side effect; it does not by
itself prove zero speculative/internal MMU or AXI requests.

## Pins And Executed Identity

All117 plan pins and all539 frozen source inputs were rechecked, together with
configuration, compiled-source manifest and complete simv/shared-library image
membership. Per-case run metadata, invocation, inputs.json, actual input.elf,
accepted SoC ELF hash/symbols and exactly one NX_SV39_PASS marker agree.
The same pin/image checks passed again after independent CSV replay.

- Image JSON SHA256: `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
- Plan SHA256: `956ff23b7a012e38930cb5947d0e5ef08b7ecaff362469227ee94afc8ca16e27`.
- Aggregate SHA256: `793a633ad9572cc5990cebb6da592f87a4cf4c02eef12b240f3eba5614b27baa`.
- [Aggregate](vcs_candidate04_01/complete.json),
  [plan/pins](vcs_candidate04_01/plan.json),
  [per-case evidence](vcs_candidate04_01/cases/).

| Trial | Completed CSV SHA256 |
| --- | --- |
| 19 | d2a5b18d9bf65dd7d67c0606fc7a9e04233dac31db595f732d539af3deca8aeb |
| 17 | a2044726f673ac064443c82ad151625dc910ebd29248e7f0dcf1053451f32e7d |
| 67 | 3295e5a65e32cd91c2224cca77a98094195abe801db1839ad2ad172d82341142 |
| 31 | adffbc0bcd7b0184719d0626d7aca1bed891ad1db9d01b978df611b71a266d3f |

Acceptance is only these four original-source-derived tuples on frozen
candidate04. It does not validate newer workspace RTL, identify the original
169/later128 error discrepancy, replace full192, or close Linux SIGSEGV,
signal-frame/context and scheduling behavior.
