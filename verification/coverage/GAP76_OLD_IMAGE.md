# Old-image floating widening coverage extension

This batch uses the user's requested old compiled image, not the live repaired
RTL. No RTL is reverted and no VCS rebuild is performed.

Baseline: `verification/out/closure90-current-20261005-01`, 654 admitted PASS tests.
Image: `verification/out/repaired-aligned-build-20260930-01/sim/simv`.
Results: `verification/out/gap76-old-image-20261006-01`.

## Directed stimuli

Eight new tests combine SEW 16/32 with:

* `vfwmul.vv`: narrow sources and widened destination.
* `vfwadd.wv`: wide first source plus narrow second source.
* `vfwsub.wv`: wide first source minus narrow second source.
* `vfwredusum.vs`: narrow vector and wide reduction seed/destination.

Each test covers LMUL 1/2, VL 1/3/5, near-capacity and capacity lengths,
all-zero/sparse/all-one masks, tail-undisturbed and mask-undisturbed policies.
Inputs are small exactly representable integers to separate datapath/control
errors from floating-point rounding-order differences. Checks cover outputs,
preserved tails and masked elements, fflags and final vstart.

The coverage hypothesis is to exercise operand-queue FP widening/narrowing
delivery, incomplete operand beats and neutral insertion for widening reduction.
The historical zero inventory identifies gaps near operand_queue.sv lines
412-451 and reduction insertion near 396-405. Reachability depends on the
specific queue instance and compiled parameters; new point gains are measured,
not inferred from an opcode being present.

Eight previously authored gap75 extension and min/max-reduction tests are also
rerun on this same old image. Their VDBs from the newer image are not reused.
Total: 16 cases, eight worker threads. Every case first runs Spike; only a
successful reference self-check proceeds to VCS. VCS admission requires full
scalar and vector differential match, DUT success and clean contract checks.
Failures and timeouts are retained separately and excluded from coverage.

## Coverage and progress

The runner unions compatible new PASS VDBs with the original 654 inputs.
It checks coverage point shape/checksum compatibility, records raw point gains
and exports a new DVE report. The export disables waivers so raw results can
be compared with raw baseline results. Old reports are not overwritten and
new repaired-image VDBs are not mixed in. This is old-RTL exploration evidence,
not current-RTL signoff.

Progress:

```sh
./vstatus jobs gap76
cat verification/out/gap76-old-image-20261006-01/status.json
tail -n 30 verification/out/gap76-old-image-20261006-01.log
```

Final report: `combined-dve/summary.csv`.
Measured gains: `raw-bitmap-delta.json`.

## Completed batch and reduction failure

The batch completed with 15 PASS and one excluded failure, producing a
669-PASS old-image aggregate. Raw additions were six line points, 19
condition points and five branch points; no FSM point was added.

`vgap76_red16` failed exactly one of its 14 reduction configurations:
LMUL=1, VL=63, all-one mask. Its seed is FP32 2.0 and source elements
are the exactly representable FP16 integers `(i % 5) - 2`. The scalar
reference and Spike give -1.0, but arch_seq=45 writes FP32 +0.0 to v16
at cycle 13424 (allocation cycle 13368). The subsequent scalar load at
PC 0x800021fe merely reads that already incorrect result. The test writes
tohost=3, confirming one self-check error rather than a checker-only mismatch.

The same LMUL=1 full-VL=64 reduction produces the correct +0.0. Element
63 is +1.0, so admitting that single tail element explains the erroneous
VL=63 result. All other tested configurations, including LMUL=2/VL=127,
match the scalar oracle. These are exact integer sums and do not admit
a one-unit discrepancy from legal unordered floating-point reassociation.

The vector trace comparator labels unordered FP reduction results
`NON_BIT_EXACT` and deliberately does not require bit-exact equality for
them. Its overall PASS is therefore not proof of this reduction's numerical
correctness. The independent scalar self-check and subsequent scalar
differential comparison reject this case; its VDB remains excluded.

### Confirmed bug: inactive tail participates in widening reduction

Status: OPEN. Recorded on 2026-10-06; repair is deferred at the user's
request. No RTL has been modified for this failure investigation.

The bounded cycle probe confirms the root cause in
`hardware/src/lane/vmfpu.sv`, in `INTRA_LANE_REDUCTION`.
`issue_element_cnt` is bounded by `issue_cnt_q`, but that counter tracks
reduction work, including neutral-fill and partial-result merging, rather
than strictly tracking remaining real source elements. During neutral-fill
source consumption, `intra_op_rx_cnt_q` advances without the corresponding
decrease of `issue_cnt_q`. Consequently the last real input beat can retain
two enabled FP32 components when only one source element is active.

Measured evidence for lane 3 of LMUL=1, VL=63 (15 active lane elements):

| Time (us) | Source progress | Work counter | Observation |
| --- | --- | --- | --- |
| 13.3925 | 0 -> 2 | 15 -> 13 | First input beat is consumed. |
| 13.3935 | 2 -> 4 | 13 -> 13 | Neutral-fill consumption advances real input progress, not the work counter. |
| 13.3945 | 4 -> 6 | 13 -> 13 | The same divergence continues. |
| 13.3995 | 14 -> 16 | 7 -> 5 | Final input handshake uses byte enable `0xff`, admitting two FP32 components instead of one (`0x0f`). |

At 13.3995 us, operand C is `0x3f80000040000000`: the low component
is valid source element 59 (+2.0), while the high component is inactive
element 63 (+1.0). FPU input valid and ready are both asserted.
The extra +1.0 changes lane 3's contribution from 0 to +1 and the final
reduction from -1.0 to +0.0. This agrees with the architectural writeback
and the independently checked self-test failure.

Future repair must distinguish the valid range of real input beats from
partial-sum merging. Simply applying the real-input remainder to every
reduction operation could incorrectly mask partial sums after source
consumption finishes. This is a repair constraint, not an implemented fix.

Probe: `verification/out/gap76-red16-probe-20261006-01`.
Evidence: `cycles/cycles.csv`, `cycles/events.csv` and
`cycles/fsdbreport.raw.csv` in that directory. The probe uses the same old
image and ELF, samples 13.2--13.55 us, and stops before test completion.
Its diagnostic VDB is not a passing test and is not admitted to coverage.

### Coverage exclusion audit

The aggregate contains the original 654 PASS inputs plus this batch's
15 PASS inputs, for 669 PASS tests. The failed `vgap76_red16/code.vdb`
is absent from both `combined-inputs.txt` (DVE input list) and the `tests`
list in `combined-bits.json` (coverage-point union). Neither the failed
test nor its diagnostic probe contributes to the reported coverage.
