# Real Quantized-KV Attention Inquiry

This is a complete six-Query-head GQA group, not a standalone dot product and
not a full-model performance claim. It uses unchanged Qwen2.5-1.5B real Decode
captures: D=128, 128 visible KV tokens, capacity=256, KV head 0, Query heads 0--5.
K is either Q8_0 or Q4_0; V is Q8_0. Both profiles use the same existing QBS ISA
and standard RVV arithmetic resources; no new quantized-AKV hardware is assumed.

## Compared Schedules

- Reference: reconstructed GGML head-major online Attention, calling the
  original production RVV Query quantizer and QK dot functions, original Q8_0
  V decoder, and production `vec.h` RVV scale/MAD helpers.
- Candidate: QBS DIRECT M4+M2, N32 QK tiles; each V row is decoded once and
  shared across all six heads. Every head retains token-order online Softmax
  and FP32 PV updates. No intermediate conversion to F16 is introduced.
- ABBA order is reference, candidate, candidate, reference. Each call includes
  Query quantization, QK/descriptor submission, online Softmax, V decoding, PV,
  final normalization, and drain. Capability discovery, test guard setup,
  comparisons, and UART output are outside the timed region for both paths.
- The reference is not an untouched full GGML operator or an end-to-end runtime
  measurement. These labels must be retained when reporting a speedup.

## Exact Parameters

The original JSON writer printed the scale as `0.0883883`. That decimal is not
an exact FP32 parameter capture. The builder verifies the pinned original
Qwen2 source expression `1.0f/sqrtf(float(n_embd_head))`, its graph forwarding,
the actual D=128 tensor shape, zero bias and zero Softcap, then evaluates that
expression in a separately recorded C probe. The resulting bits are
`0x3db504f3`. The ELF embeds the word directly. This is explicitly a parameter
derived from pinned source, not a claim that the rounded JSON contained it.

## Acceptance And Limits

1. Both ELF builds check original capture/source/tool/object hashes, exact
   tensor layouts, symbols and allocated sections. They reuse pinned unchanged
   production primitive objects, never a modified approximation of those
   functions. No on-target scalar reference is linked.
2. Native execution is gated by terminal multioutput-QK PASS. The downstream
   worker independently replays that prerequisite's raw scores and flags against
   its host oracle and rechecks its UVM/protocol evidence before starting.
3. Every trial exports all 768 output words and FP/vector CSR state. The host
   checker independently recomputes error against the unchanged original model
   golden output. Initial inquiry tolerance is absolute 0.004 plus relative
   0.002, recorded explicitly rather than described as bit-exact equivalence.
4. Same-mode repetitions must match all output bits and CSR values. Differences
   between original RVV QK and QBS are measured explicitly, including maximum
   absolute difference and differing output words; equivalence is not assumed.
5. Each shared call must execute eight successful QBS commands, with independently
   checked geometry, payload, ranges, faults and actual read/commit activity.
   Ordinary calls must execute no QBS commands. Software V-decode counts are
   checked as 768 versus 128; this is not itself a DDR-traffic measurement.
6. Actual simulator exit, checked source manifests, pinned image identity, and
   independent UVM backend/AXI read/write checks are required for terminal PASS.
   A preflight report is explicitly `PREFLIGHT_PASS_NOT_RUN`, never PASS.

Mask holes, finite additive biases, Softcap, sinks, nonfinite KV scales, other
dimensions and other layouts are outside this first inquiry. They must retain
the original runtime fallback. No GGML integration or default-enable decision
is authorized by these builds alone; that requires successful full-path results,
numerical assessment, and a reproducible benefit.

## Current Artifacts

- Q8 successor build: `verification/out/akv-quantkv-attention-q8-build-20261024-03`
- Q4 successor build: `verification/out/akv-quantkv-attention-q4-build-20261024-03`
- Complete inquiry runs: `verification/out/akv-quantkv-attention-{q8,q4}-20261024-03`
- Prerequisite successor: `verification/out/akv-quantkv-batch-qk-20261024-02`
- Worker: `run_attention.py`; raw checker: `check_attention.py`.

The original QK worker was rejected on a test-helper-induced cache assertion;
its original FAIL is retained. See `drain_probe_README.md` for the discriminating
two-ELF evidence and the exact helper-only correction. The original downstream
queues correctly refused to start and are preserved as failed gate attempts.

Each actual worker is bounded to three hours and owns independent output files.
The queue may event-wait on the prerequisite process; waiting is not execution.
If the prerequisite fails, downstream execution must not start.

Builds/runs 02 lacked initial vtype configuration before the measurement-only
drain and were interrupted, not accepted. The initialized entry and its bounded
VCS/protocol proof are documented in `attention_startup_README.md`. No RTL or
production primitive was changed by that test-entry correction.

## Accepted Q4_0 K / Q8_0 V Result

The Q4 run completed all four ABBA trials with zero simulator exit, source/image
checks and independent CVXIF/backend/AXI read/write acceptance. Raw results were
then independently replayed by the event-gated public-entry worker before it
started its own VCS execution.

| Trial | Schedule | Cycles | FCSR | VCSR | Words differing from first ordinary call |
|---|---|---:|---:|---:|---:|
| 0 | Ordinary RVV QK, head-major | 2,107,594 | 3 | 5 | 0 |
| 1 | QBS QK, shared-head | 537,059 | 3 | 5 | 0 |
| 2 | QBS QK, shared-head | 536,410 | 3 | 5 | 0 |
| 3 | Ordinary RVV QK, head-major | 2,107,097 | 3 | 5 | 0 |

Paired cycle sums are 4,214,691 versus 1,073,469: **3.926234x** speedup and
**74.530304%** cycle reduction. Every exported output word matches across all
four calls; original model golden checks also pass under the stated tolerance.
Both native calls execute the required eight QBS commands, reducing software
V-decoder calls from 768 to 128 per call without changing the decoder itself.

Receipt: `verification/akv/results/quantized-attention-q4-20261024.json`.
This is the complete specified six-head group, not whole-model performance or
the public-entry result. It does not include per-call GGML mapping/admission.
The public-entry Q4 successor is executing separately; the Q8 inquiry remains
pending at the time this result is recorded. The separately accepted RVV V
decoder is not substituted into these sealed experiments.
