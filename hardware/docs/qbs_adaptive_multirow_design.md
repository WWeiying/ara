# QBS Shape-Aware Multi-Row Reuse

## 1. Scope and decision

This work addresses a structural limitation of the original QBS execution
contract: hardware commands accepted at most four activation rows. A logical
matrix operation with `M > 4` was therefore split into independent M1--M4
commands, and every command group read the same weight matrix again.

The proposed optimization does **not** widen the 32-pair/cycle dot array, the
128-bit read path, or the 128-entry FP32 accumulator. It adds an optional
M5--M8 command geometry whose maximum result tile is `M8 x N16 = 128`
elements. The existing profile engine processes the eight activation rows as
two sequential groups of four while retaining the same four-row weight tile.
Performance comes from extending the lifetime of a weight block, not from
duplicating arithmetic resources.

The mechanism is deliberately conditional. The existing M1--M4/N32 geometry
remains the narrow-command fallback. Software may select M8/N16 only when an
ABI-derived byte cost shows that reduced weight traffic exceeds the additional
activation traffic. The GGML integration enables this conditional selection by
default and provides an explicit M4-only A/B switch. Ordinary RVV remains the
fallback for every unsupported contract.

## 2. Why fixed M4 is the relevant limitation

For direct QBS execution, let:

- `Bw` be packed bytes per weight block;
- `Ba` be bytes per activation block;
- `Kb` be the number of K blocks;
- `Tm` and `Tn` be command limits along M and N;
- `Gm = ceil(M/Tm)` and `Gn = ceil(N/Tn)` for divisible R4 output shapes.

Ignoring only the final four-row padding, command input traffic is:

```text
weight bytes     = Gm * N * Kb * Bw
activation bytes = M  * Gn * Kb * Ba
```

Changing M4/N32 to M8/N16 therefore halves weight traffic for M ranges where
the number of M groups halves, but doubles activation traffic because twice
as many N commands are needed. A valid decision must compare their sum. It is
incorrect to report the 50% weight reduction alone.

The current measured M4 counters provide two exact anchors for the model:

| Captured operator | Shape | Commands | Weight bytes | Activation bytes | Dot-active cycles |
|---|---:|---:|---:|---:|---:|
| Q4_K Attention-Q | M4, N1536, K1536 | 48 | 1,327,104 | 336,384 | 294,912 |
| Q6_K FFN-down slice | M4, N64, K8960 | 2 | 470,400 | 81,760 | 71,680 |

`verification/qbs/analyze_adaptive_tiles.py` reproduces all six values from
`config/qbs_abi.json`; its unit test fixes them as counter-contract anchors.

## 3. Exact traffic screening

The checked-in case list uses the seven layer-0 linear operators captured
from Qwen2.5-1.5B. The percentage is independent of N and K when both command
geometries divide N, but the concrete model shapes prevent a synthetic shape
from silently replacing the claimed workload.

| Profile | M | Weight change | Activation change | Total input change | Pair-capacity change | Ideal roofline change |
|---|---:|---:|---:|---:|---:|---:|
| Q4_K | 8 | -50.00% | +100.00% | -19.67% | 0% | 0% |
| Q4_K | 15 | -50.00% | +113.33% | -18.64% | 0% | 0% |
| Q6_K | 8 | -50.00% | +100.00% | -27.79% | 0% | 0% |
| Q6_K | 15 | -50.00% | +113.33% | -27.11% | 0% | 0% |

The ideal roofline is `max(padded_pairs/32, input_bytes/16)`. Its unchanged
value is material: under a perfect, uncontended 16-byte/cycle memory system,
both geometries remain compute-bound. The table proves a bandwidth and energy
opportunity, not an automatic RTL-cycle speedup. RTL retention therefore
requires measured phase counters, and publication claims must distinguish
traffic reduction from cycle reduction.

The M8 payload is one fixed eight-way interleaved block. Hardware distributes
its bytes into two four-context banks, but software does not encode two
independent M4 payloads. An M5--M7 command carries zero padding through the
inactive positions of the eight-way block. This costs at most three activation
blocks in the final wide group, but reduces input steering to shifts and masks
instead of placing a variable divide/modulo network on the 128-bit receive
path. The byte model and selection decision include this padding rather than
treating it as free.

The new geometry must never be selected for `M <= 4`: it rereads activation
blocks across twice as many N tiles without reducing weight traffic. For
larger M, the planner evaluates exact padded bytes rather than relying only on
an M threshold. This also handles tails such as M9--M15, where group-count
rounding changes the benefit.

## 4. Frozen resource envelope

The first implementation is constrained as follows:

| Resource | Existing | Adaptive mode |
|---|---:|---:|
| Signed 8-bit products per cycle | 32 | 32 |
| Read datapath | 128 bit | 128 bit |
| Weight row microtile | 4 | 4 |
| FP32 accumulator entries | 128 | 128 |
| Maximum result tile | M4 x N32 | M8 x N16 |
| Simultaneously computed activation rows | 4 | 4, in two waves |

M8 requires storage for eight current activation blocks instead of four. For
Q8_K this bounded state is 2,336 bytes for one K block, 1,168 bytes more than
the current active bank. It does not retain all K blocks and therefore does
not scale with hidden dimension. The second four-row wave reuses the current
weight buffer and existing integer/FP pipelines.

## 5. Command execution

An adaptive command follows this loop nest:

```text
for each K block:
    load one fixed eight-row activation payload (two M4 subgroups)
    for each four-row weight microtile in N16:
        load the weight microtile once
        compute activation rows 0..3 with the existing profile engine
        compute activation rows 4..7 with the same profile engine
        retain all partial sums in the existing 128-entry accumulator
commit M x N valid FP32 results
```

The two activation waves must be part of one command. Implementing them as two
ordinary M4 commands would discard the weight block between commands and
recover none of the intended reuse.

Accumulator addressing becomes geometry-dependent:

```text
M1--M4/N32: index = context * 32 + output_row
M5--M8/N16: index = context * 16 + output_row
```

Both mappings stay within 128 entries. The commit path reserves an eight-
register destination group for M5--M8, but writes only bytes containing the
logical N results; byte enables preserve the inactive register tails. This
avoids doubling VRF traffic merely because N is reduced from 32 to 16.

## 6. ABI and fallback contract

Existing encoded M1--M4 instructions retain their bit patterns. Architecture
version 3 advertises `max_M=8`, `max_results=128`, and activation-layout bit 3
for `M8_INTERLEAVED`; descriptor version 2 carries the layout without changing
its 16-byte size. The extended instruction uses a three-bit M-minus-one field,
while the descriptor remains versioned and validated before any read is
issued.

The common planner selects adaptive execution only when all of the following
hold:

- hardware advertises the architecture and M8 layout capability;
- `5 <= command M <= 8` after logical M tiling;
- the result tile is at most 128 FP32 values;
- K, profile, alignment, R4 layout, and destination register group are legal;
- exact padded `weight + activation` bytes are lower than for M4/N32 by the
  configured minimum margin.

Otherwise it emits the existing M1--M4 plan. Unknown formats and invalid
contracts continue to select ordinary RVV before `qbexec` is issued.

## 7. Production GGML integration

The public runtime decision is now consumed by the real GGML
`GGML_OP_MUL_MAT` path rather than only by directed tests. Selection is made
once for the complete operator invocation. It is intentionally restricted to
a single activation plane, an exact QBS tensor/profile binding, a direct R4
weight operation, and a K dimension that fits one hardware command. Multi-plane
operations, `MUL_MAT_ID`, split-K cases, `M <= 4`, and unsupported contracts
retain the pre-existing M4 or ordinary-RVV path.

GGML's generic quantizer naturally produces row-major Q8 blocks. For a selected
wide-M operation, the work buffer therefore has two non-overlapping regions:

```text
packed M8_GROUPED output
alignment padding
row-major Q8 staging rows
```

Worker threads quantize their rows into the staging region, synchronize, and
one worker calls the shared `qbs_pack_activation_m8_grouped()` routine. The
existing post-quantization barrier then makes the final packed region visible
before `ggml_riscv_qbs_gemm_wide()` executes the plan. M5--M7 tails are padded
only in physical storage; the logical M still controls destination commit.
This correctness-first staging pass is measurable software overhead and is not
described as free. A future direct F32-to-M8 quantizer could remove it without
changing the ISA or descriptor contract.

`GGML_RISCV_QBS_WIDE_M` is default-on. Setting it to `0` forces the legacy
M4-grouped plan for matched A/B runs. Trace output reports
`commands_m1` through `commands_m8`; the model harness rejects a run if their
sum does not equal native plus emulated command counts.

A matched-prompt native-QEMU SmolLM2-135M Q4_K_M experiment compares the legacy
and adaptive paths over the same 422 QBS `MUL_MAT` nodes and exactly
2,442,756,096 dot elements. Both execute 36,522 native and zero emulated
commands, but their command geometries differ:

| Path | M1 | M2 | M4 | M6 | M8 | Native commands |
|---|---:|---:|---:|---:|---:|---:|
| Legacy M4 | 8,046 | 4,746 | 23,730 | 0 | 0 | 36,522 |
| Adaptive M8 | 8,046 | 0 | 0 | 9,492 | 18,984 | 36,522 |

Equal command counts are expected for this M22 prompt: each M8 group replaces
two M4 groups but N16 doubles the number of output tiles. Command count alone
therefore cannot measure the optimization. Reconstructing each observed call
with canonical ABI block sizes gives the following logical
weight-plus-activation payload. It excludes descriptor, result, and software
staging traffic:

| Scope | Path | Weight bytes | Activation bytes | W+A payload bytes |
|---|---|---:|---:|---:|
| Prefill GEMM | Legacy M4 | 430,396,416 | 76,991,904 | 507,388,320 |
| Prefill GEMM | Adaptive M8 | 215,198,208 | 167,982,336 | 383,180,544 |
| Prefill+Decode | Legacy M4 | 565,719,552 | 82,552,176 | 648,271,728 |
| Prefill+Decode | Adaptive M8 | 350,521,344 | 173,542,608 | 524,063,952 |

For Prefill, weight bytes fall by 50%, activation bytes rise by 118.18%, and
their sum falls by 24.48%. Decode is unchanged, so the complete observed QBS
payload falls by 19.16%. These are ABI-derived logical payload bytes, not
measured AXI traffic. Both paths preserve QBS/RVV top-1 and generated tokens;
QEMU wall time is not used as a hardware-cycle result. The reconstruction is
reproducible with `verification/qbs/compare_adaptive_model_logs.py`, which also
rejects any mismatch in graph-node counts, modeled/traced M counts, command
counts, or dot work.

## 8. Focused RTL evidence

`rtl-adaptive-real-check` uses layer-0 Qwen2.5-1.5B captures. It retains each
operator's full reduction dimension and narrows only the output slice, so the
comparison exercises every K block while remaining a short module-level VCS
test. M4xN32 and M8xN16 both produce 128 outputs.

| Capture | Geometry | K | Cycles | Weight bytes | Activation bytes | Total payload | Prefetch wait |
|---|---:|---:|---:|---:|---:|---:|---:|
| Q4_K Attention-Q | M4xN32 | 1536 | 7,200 | 27,648 | 7,008 | 34,672 | 0 |
| Q4_K Attention-Q | M8xN16 | 1536 | 7,638 | 13,824 | 14,016 | 27,856 | 0 |
| Q6_K FFN-down | M4xN32 | 8960 | 41,939 | 235,200 | 40,880 | 276,096 | 0 |
| Q6_K FFN-down | M8xN16 | 8960 | 44,493 | 117,600 | 81,760 | 199,376 | 0 |

M8 reduces measured payload by 19.66% for Q4_K and 27.79% for Q6_K, meeting
the traffic acceptance threshold on Q6_K. It does not reduce cycles in this
ideal-memory test: both points are approximately 6.1% slower. Phase counters
attribute the complete delta to activation loading. For Q4_K, activation load
grows from 468 to 906 cycles while `compute + overlap` remains 6,336 cycles;
for Q6_K it grows from 2,731 to 5,285 cycles while `compute + overlap` remains
36,960 cycles. Weight prefetch wait is zero in all four cases, so halving
weight bytes cannot shorten the critical path under this memory model.

M7xN16 Q4_K and Q6_K tail cases also pass the same full-K functional check.
These results support a bounded bandwidth/energy optimization, not a cycle
speedup claim. A cycle benefit requires a memory regime where the eliminated
weight traffic is exposed, or a later mechanism that overlaps the command's
activation acquisition without weakening fault atomicity.

## 9. Evidence and stop conditions

The implementation is retained only if:

1. C reference, QEMU/Spike, and RTL produce results within the existing QBS
   numerical contract for real Q4_K and Q6_K M8/M15 captures;
2. strict counters equal the modeled weight, activation, useful-pair, and
   destination work;
3. at least one representative point reduces ABI-derived W+A payload by 20%
   or measured cycles by 10%; and
4. existing M1/M4, nine-profile, AKV, and ordinary-RVV representatives have
   no unexplained regression above 1%.

If RTL cycles do not improve under the current idealized L2, the result must
be reported as a traffic/energy mechanism and evaluated later under measured
latency/bandwidth sweeps. It must not be described as a cycle speedup based on
the byte model alone.

## 10. Reproduction

```bash
python3 verification/qbs/analyze_adaptive_tiles.py \
  --csv /tmp/qbs_adaptive_tiles.csv \
  --markdown /tmp/qbs_adaptive_tiles.md

python3 -m unittest verification/qbs/test_analyze_adaptive_tiles.py

python3 verification/qbs/compare_adaptive_model_logs.py \
  --baseline-log <matched-m4-qemu.log> \
  --adaptive-log <matched-m8-qemu.log> \
  --output <comparison.json>

make -C verification/qbs rtl-adaptive-real-check
```

The focused target uses a 180-second default limit per case. No synthesis,
physical implementation, full-layer VCS run, or long Prefill-Attention
simulation is part of this stage.
