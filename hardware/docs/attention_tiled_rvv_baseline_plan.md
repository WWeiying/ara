# Portable Tiled-RVV Decode-Attention Baseline Plan

## 1. Decision

The next AKV attribution target is a strong ordinary-RVV baseline, not an
immediate RTL extension. The pre-experiment measurements showed that AKV had
already removed the dominant external-memory and scalar-control repetition,
but had not changed the dot-product organization: every Q-K dot product still
performed a horizontal reduction, and the AKV path retired more vector
instructions than the original RVV loop. Those early measurements came from
different simulator builds and were used only to formulate the hypotheses;
Section 6 contains the controlled final comparison.

These observations make token-axis tiling the discriminating experiment.
Shortening local replay before this comparison would optimize one visible cost
without establishing that it remains the critical one.

## 2. Fair baseline boundary

The baseline will implement the multi-row dataflow used by optimized
VLEN-1024 RVV Attention kernels, but it will not copy a vendor memory
advantage:

- all arithmetic uses standard RVV 1.0 instructions;
- the implementation uses the same Qwen2.5 F32 Q, F16 K/V/mask, and F32 output
  captures as RVV and AKV;
- one D128/GQA6 group is processed as four Query rows followed by two Query
  rows;
- one 64-token tile is the token-axis vector, with a tail VL for KV=16;
- K is packed dimension-major and V is retained token-major once per tile, and
  both the packing instructions and ordinary-L2 scratch traffic are measured;
- no TCM, hidden context, AKV command, QBS command, custom instruction, or
  unmeasured preprocessing is allowed; and
- the output uses the existing F16 online accumulator and the same vector
  exponential approximation as the native AKV kernel where applicable.

The maximum working set for one six-head group is approximately 37 KiB: six Q
rows, six F16 output accumulators, one 128-by-64 packed K tile, one 64-by-128 V
tile, and six FP32 score rows. This is deliberately reported alongside the
6 KiB AKV context. A speed comparison without the capacity and scratch-traffic
comparison would not be fair.

## 3. Falsifiable hypotheses

### H1: per-dot reduction serialization is removable

For a tile length of 64, tile-level maximum and sum reductions should reduce
the FP reduction count from `12 * L` to at most
`2 * 12 * ceil(L / 64)`: 24, 48, and 96 reductions at effective KV lengths 16,
128, and 256. A count near the original 192, 1,536, and 3,072 means the source
did not realize the intended dataflow.

### H2: GQA reuse can be captured by ordinary RVV software

Packing one K/V tile once for all six Query heads should remove the six-way
model-tensor reread. If measured AXI traffic remains close to the original RVV
loop, ordinary-L2 scratch movement or compiler spills have consumed the
logical reuse and must be reported rather than hidden.

### H3: token-axis work improves sustained execution

At KV=128 and KV=256, the tiled baseline should materially reduce total online
cycles, retired scalar instructions, scalar-result waits, and request-blocked
cycles relative to the one-dot-at-a-time RVV baseline. A 20% cycle reduction is
the minimum threshold for calling it a stronger software baseline. Beating AKV
is not an acceptance requirement; if it does beat AKV, the result instead
becomes evidence that AKV v2 must consume token-axis semantics.

### H4: short-context setup cost is bounded

KV=16 may benefit less because packing and workspace initialization are fixed
costs. It must remain correct, and any slowdown must be attributed to measured
packing or memory activity rather than removed by a special unmeasured path.

## 4. Validation gates

The implementation advances only if all of the following hold:

1. the reference, original RVV, tiled RVV, and AKV cases use the same immutable
   capture hashes and output tolerance;
2. tiled RVV passes KV=16, 128, and 256 against the captured llama.cpp output;
3. the tiled-RVV dynamic instruction path executes no custom QBS or AKV
   instruction, even if the shared operator ELF retains an unused AKV branch;
4. the three existing phase counters cover Q conversion, measured K/V tile
   packing, and token-axis computation plus final normalization;
5. one focused RTL run confirms the intended reduction count before the long
   points are launched;
6. ordinary RVV, QBS, and AKV representative regressions remain unchanged; and
7. long simulations run in independent result directories without polling.

No RTL or synthesis change is part of this baseline node. A later AKV change
requires the measured comparison to identify a specific critical mechanism.

## 5. Implemented checkpoint

The portable path is implemented in `apps/llama_q4km_operator/main.c` and is
selected with the `tiled_rvv` implementation name. It uses only standard RVV
instructions and falls back to the existing one-row RVV path when the strict
D128/GQA6/decode shape contract is not met. Spike validation passes with the
same captured outputs at effective KV lengths 16, 128, and 256.

The first optimized build exposed compiler-generated whole-vector spills: `-O3`
fully unrolled the six-head softmax loop after inlining the vector exponential.
Keeping that loop as a non-inlined, non-unrolled function removed all
whole-register spill traffic from the main tiled loop; the remaining ten
whole-register save/restore operations occur once per tile around the scalar
`expf` call and vector-exponential temporaries. This compiler artifact was
removed before collecting the RTL baseline.

The focused KV=16 RTL run produced the following whole-operator result. Every
microarchitectural field in this table comes from the `total` counter row.

| Implementation | Cycles | Scalar inst. | Vector inst. | FP reductions | Compute-active | AXI read bytes |
|---|---:|---:|---:|---:|---:|---:|
| Original RVV | 121,338 | 35,095 | 4,694 | 192 | 7.7% | 323,840 |
| AKV | 52,318 | 3,265 | 5,578 | 192 | 23.6% | 25,728 |
| Tiled RVV | 41,293 | 7,410 | 3,662 | 24 | 14.6% | 67,904 |

The measured reduction count exactly matches H1. Tiled RVV is 2.94x faster
than the original RVV path and 1.27x faster than AKV at this short point, while
using 2.64x the AKV AXI read traffic. The result establishes that the
current AKV speedup is real but is not yet competitive with a strong
token-axis software dataflow. Section 6 confirms that this conclusion persists
at KV=128 and 256 after amortizing setup and tile packing.

The tiled path also checks that `e16,m1` can hold all 64 token lanes before it
executes. A shorter implementation therefore takes the unchanged one-row RVV
fallback instead of silently processing a partial tile; this fallback passes a
separate VLEN=512 Spike run.

## 6. Controlled final comparison

The final measurements use the same `sim_akv_m4_final/simv` binary, whose
SHA-256 is
`35fd59a6f80cdde6016a792a62e7de72e767041a4b031a303a3a71d78243c7bc`,
and the same captured Qwen2.5-1.5B Q4_K_M tensor set for each effective KV
length. All nine runs report `PASS` with zero output mismatches. Kernel cycles
come from the application's cycle interval; every other field comes from the
corresponding whole-operator `total` counter row.

| KV | Implementation | Cycles | Scalar inst. | Vector inst. | FP reductions | Compute-active | AXI read bytes | AXI write bytes |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 16 | RVV | 121,338 | 35,095 | 4,694 | 192 | 7.7% | 323,840 | 81,408 |
| 16 | AKV | 52,318 | 3,265 | 5,578 | 192 | 23.6% | 25,728 | 9,216 |
| 16 | Tiled RVV | 41,293 | 7,410 | 3,662 | 24 | 14.6% | 67,904 | 38,144 |
| 128 | RVV | 725,838 | 141,703 | 34,454 | 1,536 | 9.1% | 2,400,512 | 437,760 |
| 128 | AKV | 383,502 | 11,021 | 44,806 | 1,536 | 25.0% | 140,416 | 9,216 |
| 128 | Tiled RVV | 157,400 | 20,466 | 9,472 | 48 | 26.5% | 377,344 | 171,520 |
| 256 | RVV | 1,413,791 | 263,153 | 68,286 | 3,072 | 9.3% | 4,762,368 | 833,536 |
| 256 | AKV | 761,933 | 19,874 | 89,638 | 3,072 | 25.1% | 271,488 | 9,216 |
| 256 | Tiled RVV | 309,540 | 39,359 | 18,788 | 96 | 26.7% | 745,472 | 330,752 |

| Effective KV | RVV / Tiled RVV | AKV / Tiled RVV | RVV / AKV |
|---:|---:|---:|---:|
| 16 | 2.94x | 1.27x | 2.32x |
| 128 | 4.61x | 2.44x | 1.89x |
| 256 | 4.57x | 2.46x | 1.86x |

The result accepts all four hypotheses. The tiled path performs exactly 24,
48, and 96 reductions, replacing one reduction per Q-K dot product with two
reductions per Query row and token tile. At the long points it retires about
4.7x fewer vector instructions than AKV and reduces scalar-result waits from
12,240/24,528 cycles to 192/384 cycles. The benefit is therefore not an
artifact of short-context setup or external-memory traffic: AKV still reads
less from AXI, yet its per-token replay and per-dot reduction schedule takes
more than twice as many cycles.

The remaining cost of the software baseline is also explicit. Packing accounts
for 60,429 cycles at KV=128 and 120,809 cycles at KV=256, or 38.4% and 39.0% of
the corresponding kernel time. At KV=256 it reads 262,144 model bytes and
writes 262,144 scratch bytes during packing. The complete 36.6 KiB workspace
then produces 745,472 AXI read bytes, 2.75x AKV's traffic. This is a real cost,
not hidden preprocessing.

Current AKV instead issues 256, 2,048, and 4,096 local-load commands and
replays 64 KiB, 512 KiB, and 1 MiB through the normal LDU result path at KV=16,
128, and 256. Its replay-backpressure counter scales correspondingly from
2,048 to 16,384 and 32,768 cycles. Static inspection agrees with the counters:
`akv_attention_rvv.S` processes one token at a time, loads K plus six Q rows,
performs six D128 reductions, and then loads one V row for six output updates.
AKV solves residency, but preserves the original reduction granularity.

## 7. Integration decision and next hardware target

The tiled implementation remains a strong standalone baseline rather than a
GGML backend path. It has been validated across three context lengths but only
for one model geometry: FP16 K/V, D128, decode N=1, GQA6, prefix masking, and a
VLEN capable of 64 E16 lanes. It also uses static process-global scratch and
does not yet implement arbitrary GGML strides, worker-local storage, sinks,
ALiBi, or logit soft-capping. Integrating it now would violate the backend
selection and fallback contract. Unsupported shapes therefore continue to
take the unchanged one-row RVV path.

The evidence selects a concrete AKV-v2 target: expose a token-axis view of a
resident K tile while retaining the current D-axis row view for V. The fill
path should create that view in the local context, or provide an equivalent
banked addressing mode, so software does not perform the measured L2
transpose. One K tile must be reusable across all six GQA Query rows, and the
score path must reduce only once for maximum and once for sum per Query row and
tile. V rows may then update the six D-axis outputs as they do today. Ordinary
RVV, current AKV commands, validation, architectural VRF writes, and the RVV
fallback remain unchanged.

Acceptance for that later RTL node is measurable rather than aspirational:
preserve the 24/48/96 reduction counts, approach current AKV external traffic,
remove the 38-39% software packing phase, and beat the portable tiled baseline
without changing its numerical contract. Until a cycle-level design satisfies
those conditions, adding more replay bandwidth or another local-load shortcut
is not justified by the measured bottleneck.

Future runner invocations record the Git commit and dirty state plus capture
manifest, simulator, Spike ELF, and Ara ELF hashes in `run.conf`; the summary
CSV propagates the same fields. This closes the provenance gap that exposed the
older cross-build comparison during this experiment.
