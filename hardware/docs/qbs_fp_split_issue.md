# QBS conversion/arithmetic split issue

## Decision and scope

The FP accumulator separates the existing INT32-to-FP32 conversion unit from
the existing multiply/FMA unit at their issue and completion interfaces.
`SplitIssue=1` is the default; `SplitIssue=0` preserves the single-port
organization for paired tests. This is not a second dot array or a second FMA.
The sixteen transaction entries, 128 FP32 accumulator locations, payload SRAM,
profile formats, instruction encoding and rounding contract are unchanged.

Evidence below is command-level RTL, not complete-model or physical-design
performance. The candidate remains in the feature worktree until integration
regression. The main and FPGA RTL copies are not changed by this stage.

## Root cause

One non-affine block update needs conversion, scale multiplication and FMA.
An affine update additionally converts the correction term, multiplies its
scale and performs the correction accumulation. Originally all of these
micro-operations shared one issue and one completion interface despite using
different FPnew operation groups.

Real Q8_0 M4/N32/K896 issued 10,752 FP micro-operations in 11,055 command
cycles. The single issue port was almost saturated. Adding queue entries
would not remove this throughput limit. M1 also stalled on its fixed stream
slots with unused slots elsewhere, but eliminating those stalls alone does
not prove that command latency will decrease substantially.

The selected change supplies independent conversion and arithmetic arbiters,
each using the existing round-robin mask/LZC structure. It moves the original
conversion operation group into a conversion-only FPnew instance and disables
that group in the arithmetic instance. Pipeline depths remain one for cast
and two for ADDMUL. The additional arbitration/control cost is not yet an
area or timing measurement.

## Correctness constraints

- Each valid entry has at most one micro-operation in flight.
- Conversion states are eligible only for the conversion port in split mode;
  all other states use the arithmetic port. Both ports cannot select one entry.
- A completion advances the same entry's original state sequence. It cannot
  reorder the scale, dot accumulation or affine correction for that output.
- The existing accumulator-index conflict check prevents concurrent entries
  from updating the same output. Admission still waits for prior completion.
- Conversion completion only updates intermediate state. Final accumulator
  writes still originate from the single arithmetic completion port.
- Flags from both completion ports are ORed into sticky flags in one register
  assignment. The issue counter increments by zero, one or two.
- `busy` includes both FP pipelines. Command/fault clear remains idle-only;
  reset cancels in-flight work in both pipelines.

Assertions cover dual issue/completion tag separation, in-flight ownership,
state consistency and idle-only clear. Existing duplicate-output and
continuation assertions remain enabled. The diagnostic counters are updated
to recognize work in either port; stall observations are not an additive
breakdown of command cycles.

## Paired command results

Baseline includes the previously validated direct activation overlap
(`66e93c07`). Input vectors, weight/activation/payload byte counts, range counts
and dot work are identical within every pair.

| Real-data command | Single port cycles | Split ports cycles | Cycle reduction |
|---|---:|---:|---:|
| Q8_0 M1/N32/K896 | 3122 | 3112 | 0.32% |
| Q8_0 M4/N32/K896 | 11055 | 7250 | 34.42% |
| Q8_0 M8/N16/K896 | 11063 | 7258 | 34.39% |
| Q4_K M1/N32/K1536 | 2264 | 2262 | 0.09% |
| Q6_K M1/N32/K8960 | 17709 | 17707 | 0.01% |
| Q4_K M4/N32/K1536 | 6939 | 6925 | 0.20% |
| Q6_K M4/N32/K8960 | 40053 | 40039 | 0.03% |
| Q4_K M8/N16/K1536 | 7742 | 7728 | 0.18% |
| Q6_K M8/N16/K8960 | 45090 | 45076 | 0.03% |

The Q8_0 capture is Qwen2.5-0.5B Attention-Q, with actual model weights and
activations. Each test keeps full K and selects the indicated M/N output
slice. These are not synthetic tensors or a whole Attention-Q operator run.

Q8_0 M4 retains 10,752 FP micro-operations: 3,584 conversion operations and
7,168 arithmetic operations. It dual-issues in 3,582 cycles and completes in
7,250 cycles, close to the remaining arithmetic issue lower bound. Thus the
next improvement cannot plausibly come just from enlarging its entry table.
Any proposed removal/fusion of scale operations must separately establish the
rounding and exception contract; this change deliberately preserves it.

M1 input-slot blocking falls from 784 to zero cycles, but command latency
falls by only ten cycles. The overlap with other work explains why eliminating
a diagnostic stall count is not the same as removing critical-path latency.

## Validation and evidence

Evidence root, outside tracked source directories:

`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/qbs-shortblock-20261022/`

- `baseline/status.json` and `split/status.json`: 36 generated command cases
  at each of two memory-response-gap settings, plus nine real-data commands;
  81 functional cycle pairs, all passing and none slower. Both suite runs
  also execute the four existing fault classes. Real functional-only runs
  do not substitute for those fault tests.
- Source/image/vector/capture hashes are recorded by `run_fp_schedule.py`.
  The candidate source hashes were rechecked against the current worktree.
- Real-command `fp.csv` files contain a bounded 4,000-cycle window including
  slot, accumulator conflict, occupancy, issue, return and port state.
- `fp_equivalence_reset/run.log`: single/split accumulator comparison on
  nine profiles, two complete epochs of 512 updates each, checking every
  intermediate output bit, micro-operation count and final flags. Every cycle
  independently checks sticky accumulation of both returned exception masks.
  The run exercises 1,356 dual-return cycles and 1,278 differing-return-mask
  cycles over the two complete epochs, after resetting live pipelines.
- Inputs include signed integer values, an inexact INT32 conversion boundary,
  FP16/FP32 signed zero, subnormals, normal extrema, infinities and NaNs.
  This test proves scheduling equivalence to the prior numerical path, not
  independent IEEE correctness of the inherited FP implementation.

Run the focused test without synthesis:

```bash
make -C verification/qbs rtl-fp-split-check RTL_FP_BUILD=/new/absolute/output
```

Command regression uses `run_fp_schedule.py --help`; create a new output
directory and supply the frozen simulator image, real capture root, control
vector root and baseline evidence directory. Do not overwrite prior results.

## Remaining acceptance

Run representative full-SoC QBS and ordinary-RVV integration regression before
mainline integration. Preserve Q4_K/Q6_K controls and the fault tests alongside
the Q8_0 gain. Full-model speedup, netlist area and timing are not established
by these command-level results. No synthesis was launched in this stage.
