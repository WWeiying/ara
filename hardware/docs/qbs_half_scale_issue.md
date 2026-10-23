# QBS exact finite-half scale issue

## Motivation and acceptance gate

This candidate follows the accepted conversion/arithmetic split. The real
Q8_0 M4/N32/K896 command still takes 7,250 cycles, with 3,584 conversions,
3,584 scale multiplies and 3,584 FMAs. Conversion no longer consumes the
arithmetic port, but scale MUL and FMA still share it. Enlarging the entry
table cannot remove that issue-throughput bound.

The candidate adds a narrow multiplier, not another dot array or general FMA.
It is under verification; no native application, model-level performance or
physical result is established by the code alone. The frozen full-SoC image
used for segmented-layout testing predates this candidate and cannot validate
it. Main and FPGA RTL are unchanged.

## Exact arithmetic domain

For a finite FP16 value with exponent field E and fraction F:

```text
t = max(E, 1)
m = (E != 0 ? 1024 : 0) + F
x = (-1)^sign * m * 2^(t - 25)
```

Multiply two unsigned 11-bit mantissas into a 22-bit product P. For nonzero
P, let k be its highest set-bit index. The FP32 biased exponent is
`t_a + t_b + 77 + k`; the 24-bit significand is `P << (23-k)`.
P has at most 22 significant bits, and the nonzero value lies between 2^-48
and 65504^2. Thus every finite product is exactly representable as a normal
FP32 value: no rounding, overflow, underflow or inexact flag is needed.
Zero produces the XOR sign, including negative zero.

This domain is only the intermediate scale multiply. I2F and final FMA retain
their original rounding and exception behavior. Nonfinite halves, affine
correction profiles, and FP32 activation scales use the original FPnew path.
In particular, the existing half expansion quiets signalling NaNs without
independently raising NV; this optimization does not change that inherited
contract or claim to resolve it.

## Integration invariants

- Keep the original I2F -> scale MUL -> FMA sequence per output.
- Add one finite-half issue/return port with initiation interval one.
- Reuse the existing scale entry to hold the two original halves until their
  product returns. Add a per-entry eligibility bit, not another operand table.
- Each entry still permits only one operation in flight. The three schedulers
  select disjoint operation classes; simultaneous returns have distinct tags.
- Half-scale completion only writes its entry's intermediate product and
  addend. Only the original arithmetic completion port writes final results.
- Sticky flags still combine cast/arithmetic returns; finite-half MUL adds no
  flags. Busy includes the new pipeline, reset cancels it, and clear is idle-only.
- The added scale completion can need an accumulator read concurrently with
  a fallback scale completion. This read-mux/control cost is not assumed free.

`HalfScaleIssue=0` preserves the accepted split-issue arithmetic path;
`SplitIssue=0, HalfScaleIssue=0` preserves the original single-port reference.
The total `fp_uop_issue` counts logical FP micro-operations across all active
ports, including exact scale MUL. The testbench separately reports
`half_issue`; generic arithmetic count is total minus cast minus half issue.
The retained `dual_issue` field specifically means simultaneous cast and
generic-arithmetic issue, not every combination of two or three ports.
The no-schedulable-work probe includes the new issue class. Stall counters are
diagnostic and must not be summed as a disjoint latency breakdown.

## Validation required

1. Independent finite-half unit comparison against FPnew FP32 MUL, including
   signed zero, subnormals, normal boundaries, maximum values and reset/bubbles.
2. Three-way accumulator comparison of every intermediate output, logical
   micro-op count and final flags across all nine profiles; mixed fast/fallback
   traffic, simultaneous returns, live reset and idle clear.
3. Paired command tests using unchanged real captures, memory response delays,
   result backpressure and existing fault/recovery cases. Preserve dot work,
   traffic, result bits and flags; measure cycles and actual issue classes.
4. Rebuilt full-SoC integration before main/FPGA acceptance. Do not substitute
   a pre-candidate image or a software-model pass for this gate.

## Current test results

Evidence root:
`verification/out/qbs-half-scale-20261023/` in the verification worktree.

- `unit/run.log`: 3,688,406 finite products checked bit-for-bit against FPnew
  FP32 MUL, with zero reference exception flags. This includes all 63,488
  finite half encodings against 20 corners in both operand positions, the
  complete 1,024-by-1,024 nonnegative subnormal/zero matrix, 100,000 random
  pairs, exponent boundaries, bubbles and reset in three pipeline states.
  Two accepted transactions are deliberately cancelled by reset and accounted
  separately. VCS CPU time: 51.720 seconds.
- `accumulator/run.log`: all three configurations pass two 512-update mixed
  nine-profile epochs. Every intermediate accumulator update is bit-identical;
  final flags and logical micro-op counts agree. Per-cycle sticky flags match
  the actual cast/arithmetic returns. There are 220 half issues with overlapping
  returns, plus live half-pipeline reset and idle clear. VCS CPU: 1.580 seconds.
- `accumulator_ports/run.log`: the follow-up review adds mandatory per-port
  overlap checks. Two passing epochs observe 200 half/cast returns, 218
  half/arithmetic returns, 198 three-way returns, and 60 simultaneous fast and
  fallback scale completions reading accumulator addends. All intermediate
  outputs and flags still match the original path. VCS CPU: 1.640 seconds.
- `paired/status.json`: all 81 command pairs pass, with no cycle regressions.
  This includes 36 generated cases at each of two memory-response spacings
  and nine real-data commands. Both generated suites also exercise the existing
  fault cases. Source hashes were rechecked after completion and match the
  current candidate. Real input vectors, dot work and payload traffic are
  unchanged from the split-issue reference.

| Real-data command | Split issue | With half scale | Cycle reduction |
|---|---:|---:|---:|
| Q8_0 M1/N32/K896 | 3112 | 3111 | 0.03% |
| Q8_0 M4/N32/K896 | 7250 | 5662 | 21.90% |
| Q8_0 M8/N16/K896 | 7258 | 6130 | 15.54% |
| Q4_K M1/N32/K1536 | 2262 | 2262 | 0% |
| Q6_K M1/N32/K8960 | 17707 | 17707 | 0% |
| Q4_K M4/N32/K1536 | 6925 | 6925 | 0% |
| Q6_K M4/N32/K8960 | 40039 | 40039 | 0% |
| Q4_K M8/N16/K1536 | 7728 | 7728 | 0% |
| Q6_K M8/N16/K8960 | 45076 | 45076 | 0% |

The M4 case retains 10,752 logical micro-operations, now divided into 3,584
conversions, 3,584 exact half-scale multiplies and 3,584 generic arithmetic
operations. This removes port contention without changing dot throughput or
the accumulation order. M1 barely changes, so the multirow gain must not be
generalized to all Decode work.

Rebuilt full-SoC acceptance is still required. The new application
`llama_qwen25_q8_0_prefill_tile_qbs` selects M4/N32 with full K896 from the
real Prefill capture and uses the existing production benchmark/runtime
implementation. Its native timing includes activation quantization and command
execution, unlike the command-only measurements above. Main/FPGA acceptance
and whole-model speedup remain unclaimed.

The native acceptance worker is `verification/qbs/run_half_scale_soc.py`.
It separates `--tools-root` from `--elf-dir`, freezes binary/script/image
hashes, checks the existing source manifest, and stops on a failure or drift.
Its six host mock tests cover the build/reuse distinction, independent checker
identity, missing manifests, invalid inputs and fail-fast behavior. A reused
image is explicitly recorded as such; only a fresh build can accept the new
half-scale RTL. The four native gates are QBS/AKV handoff, ordinary RVV FMA,
real Q8_0 Decode, and the bounded Prefill tile. A separate baseline replay uses
the same frozen Prefill ELF. Neither VCS wall time nor this bounded regression
is presented as full-model speedup.

Run the first two gates with independent build directories:

```bash
make -C verification/qbs -j2 rtl-fp-split-check rtl-half-scale-check \
  RTL_FP_BUILD=/absolute/new/accumulator \
  RTL_HALF_BUILD=/absolute/new/unit
```
