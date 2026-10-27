# M4 tiled segment-store candidate: decision and measured cause

## Decision

Do not install this candidate. All tested prepared bytes, FCSR/VCSR, fallback,
guards and independent VCS protocol checks pass, but the same-ELF preparation
comparison regresses substantially. Existing production helpers, cache feature
and RTL remain unchanged. The accepted 25.09% complete-projection improvement
from exact-byte reuse is a different optimization and is unaffected.

| ABBA trial | Producer | Three-call cycles |
| ---: | --- | ---: |
| 0 | Original | 344740 |
| 1 | Tiled/segment-store | 478603 |
| 2 | Tiled/segment-store | 478315 |
| 3 | Original | 344396 |
| Paired sum | Original | 689136 |
| Paired sum | Tiled/segment-store | 956918 |

The candidate takes 38.8576% more preparation cycles, speedup 0.72016x.
These are twelve M4/K1536 preparations, not complete projection/model timings.
Parent replay reproduces the raw checker output, source pins and protocol gate.
The four-VLEN QEMU functional comparison passed 3232 cases, but did not predict
the RTL's instruction expansion or performance.

## Concrete RTL/trace evidence

`hardware/src/segment_sequencer.sv` implements segments by iterating fields and
elements. Its IDLE path changes a unit-segment store into a strided request,
with `vl=vstart+1`; SEGMENT_MICRO_OPS advances fields, then increments vstart.
The final state waits for backend idle/completion before returning. It is not
a vectorized field-interleaving store datapath. The module's original header
explicitly describes the low-IPC implementation choice.

The fresh vector trace contains:

| Allocated request tagged by original instruction | Count |
| --- | ---: |
| Candidate segment-tagged stores, `use_vd=0`, `vl-vstart=1` | 36864 |
| Same segment-tagged VRF-writing requests, `use_vd=1`, VL128 | 72 |
| Original ordinary strided stores, nf0/mop2 | 2304 |

Across six candidate producer calls, each has six blocks, two 128-element
chunks/block and one four-field architectural store/chunk. Thus 72 segment
stores expand into `72 * 128 * 4 = 36864` single-element storage requests.
The 72 VRF-writing allocations are layout work carrying the same original
instruction tag; they must not be miscounted as ordinary memory stores.
`ara_system.sv` connects monitor allocation geometry/use_vd to actual requests;
the tag alone does not describe an internal operation's behavior.

The candidate disassembly contains no whole-register vector spill/reload
instructions in its quantization body. It does contain additional sliding
and integer-reduction work. The segment expansion is a demonstrated added
cost, but the present trace does not causally assign all 267782 extra paired
cycles to it. Do not turn request counts into exclusive stall cycles.

## Implication for the next design

Fewer RVV instructions are insufficient when an instruction is internally
scalarized. A subsequent software packing design should target the current
ordinary unit-stride store path rather than assume efficient segment stores.
Any widened/packed output must still preserve exact scales, signed-max ties,
quantization bits, sixteen-element sums, caller flags and the fallback domain.
Before another timed test, inspect both the emitted code and internal mapping.

Do not fix this result by casually vectorizing the general segment sequencer:
precise faults, vstart restart, field layout, aliasing and memory ordering are
part of the ordinary RVV/Linux contract and were subjects of prior repairs.
Their redesign would require a separate architectural correctness campaign,
not an optimization hidden inside a quantizer experiment. No such RTL change
is introduced here.

Receipt: `verification/qbs/m4_prepared_reuse/tiled/review-20261027.json`.
Raw output: `verification/out/m4-tiled-soc-vcs-20261027-01`.
The failed performance candidate remains available for reproducibility, not
as a recommended runtime option.
