# Decode Attention/KV Streaming Baseline

## 1. Purpose and evidence rules

This document freezes the pre-optimization baseline for the shape-driven
Attention/KV mechanism. It answers one question before any DUT change: which
repeated work in a real llama.cpp Decode Attention loop is both substantial and
removable by a small cooperation mechanism that reuses the existing RVV
lanes, MFPU, VLSU, MMU/AXI, VRF hazards, and completion path?

Three evidence classes are kept separate:

1. **Strict workload facts** come from captured tensor metadata and the C loop.
   They include shapes, effective KV length, query count, dot-product count,
   and the logical bytes that the source must read or write.
2. **Dynamic ISA facts** come from a Spike instruction trace of the same ELF.
   They establish how the compiler realizes the loop, including whole-register
   scratch reloads, reductions, and vector-to-scalar transfers.
3. **RTL diagnostics** come from `llm_perf_monitor`. Cycle counts, phase
   boundaries, request handshakes, functional-unit activity, queue pressure,
   scalar-result waits, and AXI handshakes retain their literal RTL meaning.
   Ara request counts are not assumed to be ISA instruction counts.

In particular, `unit_load_span_bytes` and `unit_store_span_bytes` are not used
as strict byte totals here. The monitor computes an ordinary unit-stride span
from `vl`, `vsew`, and `nf`; Ara represents a whole-register load with an
already expanded `vl`, so multiplying by `nf + 1` again overstates that span.
The field remains useful only as a run-to-run diagnostic until whole-register
operations receive a separate accounting rule.

## 2. Real llama.cpp workload

The source workload is Qwen2.5-1.5B Instruct Q4_K_M, layer 0, first Decode
evaluation after prefill. The capture callback is restricted to five coherent
Attention boundaries from one model execution:

- `attn_q_input-0`: F32 query, shape `[128, 1, 12, 1]`.
- `attn_k_input-0`: F16 post-update key-cache view, shape
  `[128, 256, 2, 1]`.
- `attn_v_input-0`: F16 post-update value-cache view, the same shape as K.
- `attn_mask_input-0`: F16 mask, shape `[256, 1, 1, 1]`.
- `kqv_out-0`: F32 Attention result before output projection, shape
  `[1536, 1, 1, 1]`.

The model therefore has head dimension `D = 128`, 12 query heads, two KV
heads, and a GQA group size of six query heads per KV head. One query token is
evaluated in each case. Prompts of 15, 127, and 255 tokens produce effective
post-update KV lengths `L = 16`, `128`, and `256`. Inactive capacity entries
remain in the captured 256-entry tensor and are rejected by the mask.

The reproducible capture set is selected by:

```text
/home/wangwy/llama/captures/
  qwen2.5-1.5b-q4_k_m-attention-contexts-latest
```

For this milestone, that link resolves to the immutable local set
`qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252`.

| Provenance item | Value |
|---|---|
| Model SHA-256 | `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e` |
| llama.cpp source commit | `316e72d38da2bf9af84f946fb6e99419d80849f9` |
| Capture source SHA-256 | `5e8aa57bed672334ed2e1bfff59f759927aa6e22363038138d73a92705c934d7` |
| Capture binary SHA-256 | `d358aa6b90dca70d1971fca3ad8f6dec30e1d84c8d10bd9b6ef6eca32f2f210c` |

The llama.cpp worktree was dirty at capture time, so the source-file and
binary hashes, rather than the commit alone, identify the executable behavior.

Each case records the model hash, capture-binary hash, llama.cpp source commit,
capture-source hash, prompt, token count, runtime context, and SHA-256 of all
five tensors. `capture-attention-contexts.sh` verifies all metadata before it
updates the `latest` link.

## 3. Current RVV computation

For every query head, the benchmark converts one F32 Q vector to F16 and clears
one F16 output accumulator. It then scans the mask. For each active KV entry it
performs:

```text
score_i = scale * reduce_sum(FP32(K_i * Q)) + mask_i
m_new   = max(m_old, score_i)
l_new   = l_old * exp(m_old - m_new) + exp(score_i - m_new)
O_new   = O_old * exp(m_old - m_new) + V_i * exp(score_i - m_new)
```

The implementation is numerically stable online Softmax, but its software
materialization exposes four kinds of repetition:

1. `dot_f16_rvv()` reloads the same 256-byte F16 Q vector for every active KV
   entry.
2. GQA processes six query heads serially, so each 256-byte K vector and each
   256-byte V vector for one KV head are read six times.
3. Every V update loads and stores the 256-byte F16 accumulator. A new running
   maximum triggers an additional full accumulator load/scale/store pass.
4. Every dot product reduces its FP32 partial vector and transfers one scalar
   score to the scalar core before the next online-Softmax decision can
   proceed.

The compiler also materializes the zero-initialized FP32m2 dot accumulator on
the stack once and reloads it with `vl2re8.v` before each dot product. This is a
software scratch transfer, not a model tensor transfer.

## 4. Strict operation and traffic model

There are 12 query vectors and `12L` dot products. With F16 Q/K/V and
`D = 128`, one vector occupies 256 bytes. The following terms are strict for
the current source access pattern, except that accumulator rescaling is
deliberately excluded from the stated lower bound:

```text
Q_stream       = 12L * 256
Q_resident     = 12  * 256
KV_stream      = 2 * 12L * 256
KV_GQA_reuse   = 2 * 2L * 256
accum_RMW_min  = 2 * 12L * 256
current_min    = Q_stream + KV_stream + accum_RMW_min
resident_min   = Q_resident + KV_GQA_reuse
```

`resident_min` assumes Q remains local for one head, one K/V pair is loaded
once for all six query heads in its GQA group, and online-Softmax accumulators
remain local. It excludes the compulsory final output store from both sides.
It is therefore a mechanism-specific lower bound rather than predicted AXI
traffic.

| Effective KV | Dot products | Mask skips | Current targeted lower bound | Resident/reuse lower bound | Reduction opportunity |
|---:|---:|---:|---:|---:|---:|
| 16 | 192 | 2,880 | 245,760 B | 19,456 B | 12.63x |
| 128 | 1,536 | 1,536 | 1,966,080 B | 134,144 B | 14.66x |
| 256 | 3,072 | 0 | 3,932,160 B | 265,216 B | 14.83x |

The opportunity does not imply equal cycle speedup: exponential evaluation,
lane arithmetic, control, memory latency, queue capacity, and final
normalization remain. It does show that the repetition grows with context and
is large enough to justify a bounded resident-state mechanism.

Streaming Spike counts over the three already validated ELFs give the
compiled-code additions below. `Observed target` includes the data-dependent
accumulator rescale passes, while `dot scratch` is listed separately because it
is compiler materialization rather than model data or online state.

| Effective KV | Whole reload / reduction / scalar return | Widening MAC | Accumulator rescales | Observed target | Dot scratch load |
|---:|---:|---:|---:|---:|---:|
| 16 | 192 / 192 / 192 | 384 | 77 | 285,184 B | 49,152 B |
| 128 | 1,536 / 1,536 / 1,536 | 3,072 | 125 | 2,030,080 B | 393,216 B |
| 256 | 3,072 / 3,072 / 3,072 | 6,144 | 135 | 4,001,280 B | 786,432 B |

## 5. Measured RTL baseline

The RVV implementation passes against the captured llama.cpp golden output at
all three effective KV lengths. Their first-order RTL signatures are:

| Effective KV | Total cycles | Online cycles | Online share | Compute-active share | Scalar retired share |
|---:|---:|---:|---:|---:|---:|
| 16 | 137,985 | 130,344 | 94.46% | 6.66% | 88.23% |
| 128 | 803,823 | 796,177 | 99.05% | 8.23% | 80.24% |
| 256 | 1,558,923 | 1,551,299 | 99.51% | 8.39% | 79.18% |

At L=16, the online phase retires 33,969 scalar instructions out of 38,501
total phase instructions. At L=128 it retires 139,233 out of 173,525. The
L=256 case retires 259,147 scalar instructions out of 327,271. The small
compute-active shares are measured execution-fire activity, not merely a
lane-busy proxy; they show that the existing arithmetic datapath is idle for
most of the hotspot despite the large arithmetic workload. The retirement
probe counts committed CVA6 instructions, and classifies as vector only the
committed entries whose functional unit is `ariane_pkg::ACCEL`; vector
retirement is therefore a strict subset of total retirement rather than an Ara
request proxy.

The L=16 phase issues 192 FP reductions, exactly one for each of the 12 x 16
dot products. The reduction-state probe is active for 9,216 cycles, exactly 48
cycles per serialized reduction, and records 768 explicit scalar-result wait
cycles. At L=128 the same invariants scale to 1,536 reductions, 73,728
reduction-state cycles, and 6,144 scalar-result wait cycles. These are different
quantities: reduction activity covers the lane reduction protocol, while
scalar-result wait covers only the final sequencer-visible return wait.
At L=256 the same invariants hold for 3,072 reductions, 147,456 reduction-state
cycles, and 12,288 scalar-result wait cycles. Thus all three cases spend exactly
48 reduction-state cycles and four explicit result-wait cycles per dot product.

The Spike trace independently contains:

- 192 `vl2re8.v` whole-register accumulator reloads;
- 192 `vfredusum.vs` reductions;
- 192 `vfmv.f.s` vector-to-scalar transfers;
- 384 `vfwmacc.vv` instructions, two VLEN=1024 chunks per 128-element dot.

It also contains 89 `vfmul.vf` instructions. Twelve are the final output
normalizations, leaving 77 data-dependent online accumulator rescale passes.
The online accumulator therefore transfers `(192 + 77) x 2 x 256 = 137,728`
bytes, and the observed targeted Q/K/V/accumulator traffic is 285,184 bytes.
The 192 whole-register scratch reloads add another 49,152 bytes outside that
algorithmic category. These are logical source/ISA bytes; AXI burst bytes are
reported separately and can include transfer-granularity effects.

The L=128 and L=256 traces preserve the same one-to-one whole reload,
reduction, and scalar-return counts at 1,536 and 3,072 respectively. This
correspondence rules out a counter-classification artifact. The trace and
source jointly show that the scalar feedback boundary is paid for every dot
product, while RTL shows that the entire online loop dominates the task.

The request-side pressure also scales with active KV work:

| Effective KV | Request-blocked cycles | Blocked share | Queue-full cycles | Hazard-block cycles | AXI read / write bytes |
|---:|---:|---:|---:|---:|---:|
| 16 | 38,067 | 29.21% | 5,376 | 5,186 | 325,072 / 68,864 |
| 128 | 290,823 | 36.53% | 43,008 | 41,474 | 2,467,024 / 425,216 |
| 256 | 578,431 | 37.29% | 86,016 | 82,946 | 4,902,768 / 820,992 |

These fields retain their literal interface meanings. In particular, the AXI
totals include cache-line and transfer-granularity behavior and are not a
replacement for the strict source-level traffic model. Their near-linear
growth from L=128 to L=256 is nevertheless consistent with the repeated
logical accesses reaching the memory system rather than being eliminated by
the current execution path.

## 6. Root-cause hypotheses and discriminating evidence

The implementation phase will proceed only against the following falsifiable
hypotheses:

| ID | Hypothesis | Distinguishing observation |
|---|---|---|
| H1 | Online cycles scale primarily with active KV work. | From L=16 to 128 and 256, online cycles should track `12L`; masked-capacity scanning appears separately as scalar overhead. |
| H2 | Per-dot reduction is serialized by scalar score consumption. | Reduction count must equal `12L`; each next Softmax decision follows `vfredusum` and `vfmv.f.s`, with no independent dot stream crossing that boundary. |
| H3 | Q is not resident across the KV loop. | Dynamic Q-side vector loads and the source address repeat once per active KV entry for a query head. |
| H4 | GQA reuse is lost across query heads. | The same K/V address range is revisited six times, once per query head mapped to the same KV head. |
| H5 | Online output state is repeatedly materialized in memory. | Every active KV entry causes one accumulator load/store pair; score maxima cause extra scale load/store pairs. |
| H6 | Compiler scratch reload adds one whole-register transfer per dot. | `vl2re8.v` count equals dot-product count and reloads the same stack slot before each pair of `vfwmacc.vv`. |

H1 is confirmed by the L=16/128/256 RTL sweep: once masked scanning ceases to
dominate, doubling active KV work from 128 to 256 increases online cycles by
1.95x. H2 and H6 hold at every length by exact dynamic instruction count and
the strict reduction-state/result-wait invariants. H3-H5 follow from the source
address expressions and compiled load/store counts; a focused address trace is
still required before implementation to verify the temporal reuse windows and
to size bounded resident storage, not to infer byte totals from AXI bursts.

## 7. Design implication, not yet an implementation

The evidence supports a narrow cooperation mechanism rather than a second
vector processor. A candidate command should describe the Attention shape and
memory streams, retain one Q vector and the GQA head group locally, stream each
K/V tile through existing VLSU/MMU paths, and keep online maximum, normalization
sum, and output accumulators local until final commit. Existing lanes/MFPU
remain the arithmetic engine, and ordinary RVV remains the fallback.

There is also a stronger software comparison point in the local llama.cpp
tree. `ggml-cpu/spacemit/rvv_kernels.cpp` contains VLEN=1024 F16 Attention
kernels with `QLEN=2/4`. When TCM scratch is available, they pack a token-major
K tile into dimension-major form, accumulate several vectors of KV-position
scores with `vfwmacc.vf`, apply tile-level Softmax, and reuse each V vector
across multiple query rows. This changes the vectorization axis and reduces
horizontal reductions from one per dot product to a small number per tile.

That implementation is not the generic RISC-V llama.cpp path measured above,
and it assumes vendor dispatch plus a suitable TCM buffer. Nevertheless, the
dataflow transformation is software prior art within the evaluated codebase.
The hardware mechanism must therefore be judged against an Ara-compatible
multi-row tiled RVV baseline as well as the generic path. A defensible hardware
contribution is narrower: consume shape at the command boundary, perform
on-path K tile organization and bounded GQA reuse without requiring external
TCM/repack traffic, retain online state across tiles, and remove instruction
and scalar-control serialization while using the existing vector arithmetic
datapaths.

No decision has yet been made to add a dedicated reduction or exponential
pipeline. That addition is allowed only if the completed context sweep and
cycle-level dependency trace show those operations remain critical after the
measured data-movement repetition is removed.

## 8. Reproduction

```bash
# Capture and validate coherent real-model tensors.
hardware/scripts/llama_q4km_extract/capture-attention-contexts.sh

# Functional checks for one context.
hardware/scripts/llama_q4km_extract/run-ara-attention-core.sh rvv 128 --spike-only
hardware/scripts/llama_q4km_extract/run-ara-attention-core.sh ref 128 --spike-only

# RTL run; use a separate background invocation for long contexts.
hardware/scripts/llama_q4km_extract/run-ara-attention-core.sh rvv 128 --ara-only

# Collect literal counters and the strict/source-derived baseline model.
hardware/scripts/llama_q4km_extract/summarize-ara-attention-core.py
hardware/scripts/llama_q4km_extract/analyze-attention-baseline.py
```

Generated captures, builds, simulation directories, traces, and reports are
not versioned. Source, scripts, monitor wiring, counter definitions, and this
evidence contract are versioned together.
