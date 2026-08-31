# Portable Tiled-RVV Decode-Attention Baseline Plan

## 1. Decision

The next AKV attribution target is a strong ordinary-RVV baseline, not an
immediate RTL extension. The current D128/GQA6 measurements show that AKV has
already removed the dominant external-memory and scalar-control repetition,
but has not changed the dot-product organization:

| Effective KV | Implementation | Online cycles | Scalar inst. | Vector inst. | FP reductions | Compute-active | AXI read bytes |
|---:|---|---:|---:|---:|---:|---:|---:|
| 16 | RVV | 130,344 | 33,969 | 4,532 | 192 | 6.7% | 325,072 |
| 16 | AKV | 46,295 | 1,142 | 5,428 | 192 | 25.4% | 19,584 |
| 128 | RVV | 796,177 | 139,233 | 34,292 | 1,536 | 8.2% | 2,467,024 |
| 128 | AKV | 377,303 | 8,786 | 44,656 | 1,536 | 25.3% | 134,272 |
| 256 | RVV | 1,551,299 | 259,147 | 68,124 | 3,072 | 8.4% | 4,902,768 |
| 256 | AKV | 755,607 | 17,522 | 89,488 | 3,072 | 25.2% | 265,344 |

AKV therefore removes more than 90% of the measured RVV read traffic at the
long points, while every Q-K dot product still performs a horizontal
reduction. Its remaining online work also retires more vector instructions
than the original RVV loop. These observations make token-axis tiling the
discriminating next experiment. Shortening local replay before this comparison
would optimize one visible cost without establishing that it remains the
critical one.

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

The focused KV=16 RTL run produced the following result:

| Implementation | Cycles | Scalar inst. | Vector inst. | FP reductions | Compute-active | AXI read bytes |
|---|---:|---:|---:|---:|---:|---:|
| Original RVV | 130,344 | 33,969 | 4,532 | 192 | 6.7% | 325,072 |
| AKV | 46,295 | 1,142 | 5,428 | 192 | 25.4% | 19,584 |
| Tiled RVV | 41,293 | 7,410 | 3,662 | 24 | 14.7% | 67,904 |

The measured reduction count exactly matches H1. Tiled RVV is 3.16x faster
than the original RVV path and 10.8% faster than AKV at this short point, while
using 3.47x the AKV external read traffic. The result establishes that the
current AKV speedup is real but is not yet competitive with a strong
token-axis software dataflow. KV=128 and 256 determine whether that conclusion
persists after amortizing setup and tile packing.
