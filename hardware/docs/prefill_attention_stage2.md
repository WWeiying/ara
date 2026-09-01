# Prefill Attention Stage-2 Baselines and Long-Prompt Evidence

## 1. Purpose and evidence boundary

This stage freezes the software baselines that a Prefill hardware extension
must beat. It uses tensors captured at the `attention_core` boundary of a real
llama.cpp execution of `Qwen2.5-1.5B-Instruct-Q4_K_M`. The stage does not add
an instruction or change RTL. It separates four kinds of evidence:

1. captured tensor topology and numerical goldens;
2. exact algorithmic work and model-payload traffic;
3. Spike correctness of the ordinary and tiled RVV implementations; and
4. cycle-accurate RTL measurements, which are reported only when they exist.

Calculated K/V bytes below are logical reads of the captured K/V payload. They
are not AXI-byte measurements and do not include scratch, instruction, mask,
Query, output, cache-line, or write traffic.

## 2. Real captures

The first long-prompt execution contains two real llama.cpp Prefill chunks:

| Chunk | M | P | D | Hq | Hkv | GQA | Physical KV | Active prefixes |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 512 | 0 | 128 | 12 | 2 | 6 | 512 | 1..512 |
| 1 | 511 | 512 | 128 | 12 | 2 | 6 | 1024 | 513..1023 |

A second execution captures a single target Prefill call with `M=1024` and
`P=0`. llama.cpp also emits a two-token warm-up chunk and an eight-token chat
template tail; those calls are retained in the capture but are not substituted
for the target call.

A third execution uses a 2,560-token real prompt and captures five consecutive
512-token chunks. Its fifth chunk supplies the required `P=2048, M=512` case;
smaller `M` cases at the same past-token length are Query-prefix slices of that
real call, not padded or repeated tensors.

All target tensors are contiguous and use:

- F32 Query `[128,M,12,1]`;
- F16 Key and Value `[128,KV,2,1]`;
- F16 causal mask `[KV,M,1,1]`; and
- F32 golden output `[1536,M,1,1]`.

The packager checks every mask row. Its finite prefix must contain exactly
`P+i+1` entries for Query token `i`, followed only by F16 negative infinity.
It also rejects nonpositive scale, nonzero ALiBi bias, nonzero logit soft-cap,
inconsistent GQA topology, noncontiguous strides, and incorrect byte counts.

The durable capture roots are:

```text
/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-prefill-1023-20260901
/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-prefill-m1024-20260901
/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-prefill-p2048-20260901
```

## 3. Query-prefix matrix

`build_prefill_attention_matrix.py` derives smaller Query-prefix cases without
inventing tensor values. It slices only Query, mask, and golden tensors along
the Query-token axis and retains the complete captured K/V payload. K/V files
are hard-linked when the filesystem permits it. Each case records source-case
and source-manifest hashes.

The current matrix contains 16 real-data cases:

```text
P=0:    M=15,64,128,256,512,1024
P=512:  M=15,64,128,256,511
P=2048: M=15,64,128,256,512
```

Its versioned root and stable symlink are:

```text
/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-prefill-matrix-v3-20260901
/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-prefill-matrix-latest
```

## 4. Frozen baseline schedules

### 4.1 Ordinary RVV

The ordinary implementation processes one Query head at a time. For each
causally visible K/V token it computes one Q-K dot product, updates online
softmax state, and accumulates the corresponding V row. It is the portable
fallback and retains only one Query-head state, but it rereads each K/V prefix
once for every Query head.

### 4.2 Existing-command serial AKV-v2

The compatibility implementation processes one `(Query token, KV head)` pair
per AKV-v2 context. Six GQA Query rows share the K/V resident in that context,
so it removes the sixfold GQA reread. However, FULL/REFILL/RELEASE and the
entire K/V prefix are repeated for every Query token. This is a real baseline
using the existing ABI, not the proposed Prefill mechanism.

### 4.3 Query-tiled ordinary RVV

The strong RVV baseline uses a four-Query tile for D128/GQA6. For each KV head
it:

1. converts four sets of six Query rows to F16 and initializes 24 online
   softmax states with F32 numerator, maximum, and denominator state;
2. advances through 64-token K/V tiles up to the largest causal prefix in the
   four-Query group;
3. packs each K/V tile once, then computes only the visible portion for each
   Query token;
4. performs tile-level maximum and sum reductions; and
5. stores four sets of six F32 output rows.

The implementation uses only standard RVV instructions. Its fixed logical
working set for the D128 path is approximately 56 KiB: 6 KiB of F16 Query,
12 KiB of F32 output-numerator state, 32 KiB of active K/V tile data, 6 KiB of
score rows, and scalar maximum/denominator state. The compiled application
reserves larger static arrays to retain the separate D256 fallback, so ELF
capacity and logical algorithm state are reported separately.

Unsupported D/GQA/VLEN shapes use the unchanged one-row RVV fallback. D256
remains an M=1-only comparison and is not admitted as a long-Prefill fast path.

## 5. Exact work and K/V payload traffic

For a causal case, let

```text
S = sum(P+i+1), i in [0,M)
T4 = sum(maximum visible prefix in each four-Query tile)
```

With D128, Hq=12, Hkv=2, and F16 K/V, one K+V token for one head is 512 bytes.
The schedules therefore read:

```text
ordinary RVV:  S  * Hq  * 512 bytes
serial AKV-v2: S  * Hkv * 512 bytes
tiled RVV:     T4 * Hkv * 512 bytes
unique floor:  (P+M) * Hkv * 512 bytes
```

| Case | Attention MACs | Ordinary RVV K/V | Serial AKV-v2 K/V | Tiled RVV K/V | Unique K/V floor |
|---|---:|---:|---:|---:|---:|
| P0, M15 | 368,640 | 737,280 B | 122,880 B | 39,936 B | 15,360 B |
| P512, M15 | 23,961,600 | 47,923,200 B | 7,987,200 B | 2,137,088 B | 539,648 B |
| P0, M512 | 403,439,616 | 806,879,232 B | 134,479,872 B | 33,816,576 B | 524,288 B |
| P0, M1024 | 1,612,185,600 | 3,224,371,200 B | 537,395,200 B | 134,742,016 B | 1,048,576 B |

At P0/M512, query tiling removes 23.86x of ordinary-RVV K/V payload reads and
3.98x of serial-AKV reads. It remains 64.5x above the unique-payload floor.
This residual is the specific reuse opportunity for a K/V-tile-outer,
Query-tile-inner hardware schedule; it is not evidence that such a schedule is
already cycle efficient.

## 6. Numerical contract and measured failure analysis

The original vector exponential built an exponent bit pattern without handling
inputs below the normal F32 range. In the real P512/M15 capture, Query head 3
has a score spread of approximately 232.7. Some exponent inputs are therefore
below -104, where that construction is not valid. The observed signature was
all 1,920 output elements for that head becoming NaN.

The corrected implementation first identifies values below `ln(FLT_MIN)`,
clamps the polynomial input to that boundary, and explicitly merges zero into
the underflow lanes. This is the same numerical rule used by the native AKV-v2
kernel. The fix removes the NaNs and does not change the finite-range
polynomial.

An independent NumPy implementation then recomputed all 16 cases with stable
F32 softmax directly from the captured tensors. Every complete output passed.
The global maximum absolute difference from the llama.cpp golden was
`5.2195e-5`; at `rtol=0.002`, the largest required absolute tolerance was only
`8.553e-6`. This disproves the earlier claim that the captured operator itself
required `atol=0.012`.

Focused emulation and Spike diagnostics instead locate the long-context error
in the implementation's F16 online output numerator. On the eight failing
tiled M1024 elements, F16-state emulation reaches `0.0169867` maximum error,
matching Spike's `0.0169744`; retaining F32 state reduces the same emulation to
`1.252e-5`. Rounding each softmax weight to F16 does not explain the failure.
The implementation therefore keeps Query/K/V storage in their captured types
but uses F32 maximum, denominator, and output-numerator state. Recorded
tolerances must describe the GGML contract and may not be widened to hide
reduced-precision state drift.

This F32-state rule applies to multi-token Prefill. Existing single-token
Decode captures were produced against the earlier F16 numerator schedule, and
changing that rounding sequence causes a one-element tolerance failure on the
real Gemma D256/GQA4 capture even though its layout and indexing are correct.
The benchmark therefore dispatches `M=1` Decode to the frozen F16-state
schedule and `M>1` Prefill to the F32-state schedule. This preserves the
established Decode contract without weakening the long-Prefill numerical
contract or widening either tolerance.

## 7. Current validation status

| Case | Implementation | Platform | Result | Evidence |
|---|---|---|---|---|
| Decode, D128/GQA6, M1/KV16 | tiled RVV | Spike | PASS | frozen Decode-state regression |
| Decode, D256/GQA4, M1/KV17 | reference/RVV/tiled RVV | Spike | PASS | real Gemma capture; all three paths |
| P0/M15 | tiled RVV | Spike | PASS | short Prefill regression |
| P512/M15 | ordinary RVV | Spike | PASS | complete captured output |
| P512/M15 | tiled RVV | Spike | PASS | complete captured output |
| P0/M512 | ordinary RVV | Spike | PASS | complete captured output |
| P0/M512 | tiled RVV | Spike | PASS | complete captured output |
| P0/M1024 | ordinary RVV | Spike | PASS | complete strict output; `atol=0.004`, `rtol=0.002` |
| P0/M1024 | tiled RVV | Spike | PASS | complete strict output; F32 Prefill state |

Spike reports correctness only because `cycle` is intentionally zeroed in the
Spike build. The complete P0/M512 checks are not RTL cycle measurements. The
only current Prefill RTL cycle point remains the matched-L2 P0/M15 comparison
documented in `prefill_attention_stage1.md`.

The M1024 application occupies 21.85 MiB above `0x80000000`; Query, golden,
and output alone consume 18 MiB. It therefore cannot be run on the existing
16 MiB simulator without aliasing. A later M1024 RTL run requires an explicitly
recorded 32 MiB simulation-only L2 build. This capacity change does not alter
the architectural cache hierarchy claimed by the design.

## 8. Falsifiable hardware hypothesis

The retained hypothesis is that a bounded Prefill mechanism should keep one
64-token K/V tile resident while applying multiple Query groups, rather than
restarting the context for each Query token. The retained implementation uses
a fixed 64-Query software block and existing FULL/REFILL commands; the measured
Query-only context-update alternative was slower and has been removed.
Online-softmax state resumes across K/V tiles, and storage is fixed by the
Query-block limit rather than scale with M, P, or context length.

The following cycle-level evidence distinguishes the expected bottleneck from
alternatives:

- external Query, K/V, mask, state, and output bytes as separate strict
  counters;
- FULL, REFILL, row/column replay, and RELEASE command counts;
- resident K/V tile reuse count and K/V fill cycles;
- online-softmax state spill/reload bytes and cycles;
- QK/PV MAC work, maximum/sum reduction counts, and reduction wait cycles;
- VLSU request, replay, and backend-ready blocked cycles; and
- total cycles with an unchanged complete golden comparison.

If K/V bytes fall but state traffic or reductions become the critical path,
the result rejects a K/V-only explanation. Additional semantics are justified
only by that measured transfer of the bottleneck.

## 9. Remaining Stage-2 gates

Before changing RTL, this stage still requires:

1. measured serial-AKV and tiled-RVV cycle attribution at a discriminating
   feasible point; and
2. one real M>=512 all-operator RTL point once the winning bounded mechanism
   is available, because the current software baselines alone are too long to
   use as the final hardware result.

No Stage-2 traffic projection is promoted to a performance claim until these
gates are closed.
