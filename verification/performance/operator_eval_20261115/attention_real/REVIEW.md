# Operator Plan Review

## Prepared Real Coverage

| Model | Layer | Source Q/KV Heads | Actual Query Heads / KV Head | D | Prompt / Visible Decode KV | Capacity |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen3 1.7B Q4_K_M | 0 | 16/8, GQA2 | 0,1 / 0 | 128 | 136 / 137 | 256 |
| Qwen3 1.7B Q4_K_M | 0 | 16/8, GQA2 | 0,1 / 0 | 128 | 512 / 513 | 768 |
| Qwen3 1.7B Q4_K_M | 0 | 16/8, GQA2 | 0,1 / 0 | 128 | 1024 / 1025 | 1280 |
| Llama 3.2 1B Instruct Q4_K_M | 0 | 32/8, GQA4 | 0,1 / 0, a two-head slice | 64 | 128 / 129 | 256 |

All four use genuine captured queries, all visible K/V rows, original full
causal mask, actual F16 cache operands, and the captured model's exact
1/sqrt(D) scale rounded to F32. No KV repetition or dimension rotation. Each
operand extraction is pinned and strided; no original model input script or
live historical RTL/documentation inventory is inherited. Model files retain
their recorded SHA identities. Fresh captures are host-only, not RTL evidence.

This is NOT coverage of all model heads, complete Llama GQA4, multiple KV
groups, layer diversity, native D96/D256, contexts beyond KV1025, sliding or
noncausal masks, Prefill/query tiles, batches, paged/quantized KV, sinks,
softcap/ALiBi, non-RNE, nonzero vstart, or GGML graph integration. Prior
derived D96/GQA3/tail tests remain controlled structural tests, not real-model
performance points and are not reissued here. Next meaningful expansion is
full captured head groups, second/middle/last layers, genuine native D96/D256
models, real long-context Prefill, then GGML selection/fallback and end-to-end.

## Strong RVV Fairness

Five timed arms retain identical query conversion, full KV/softmax work,
strict math, head mapping, SDK planner/preflight and output normalization.
The established full_call baseline is its archived optimized panel4 QK plus
the exact rotating-register PV body, not the weaker diagnostic rvv.c. Its
AKV panel/row replay loads are explicitly labeled; presenting it as ordinary
memory RVV would be incorrect. A separate ordinary-memory adaptation preserves
that arithmetic/register schedule, replaces replay with ordinary loads, and
includes K transpose in ROI. Native SDK auto is retained as a third reference.
The memory adaptation is prepared and independently gold-checked, not yet a
measured/accepted "strongest memory baseline" or a recreation of every old
paper/compiler configuration. No speedup is accepted merely by compilation.

All arms share pinned compiled SDK softmax; no shortened K, weaker arithmetic,
reused prefix golden, or excluded packing to inflate speedup. Original T137
must reproduce the established independent SHA. Fresh gold uses SoftFloat
plus audited target-newlib scalar expf, not rounded JSON or host glibc.
Every model output must satisfy fixed atol0.003 + rtol0.02*abs(model).
Calibration order is 0,1,4,2,3. Symmetric order is supported with `--order
balanced`; the four delivered calibration firmwares alone do not eliminate
warm-state/order bias. Parent must run reviewed symmetric repetitions before
performance claims, keeping the all-on image, flags and simulator-slot cap.

## Resident And Cost Boundaries

Resident can remove repeated per-column/per-row dispatch, replay and vector
instruction scheduling by consuming the same QK/PV FMA work in its private
execution path. It does not remove required external Q/K/V transfers, online
softmax, coefficients, F16 PV semantics, workspace initialization, final
normalization, FULL/REFILL/RELEASE, or target integration costs. Each arm's
actual SDK/leaf entries, command signatures, external bytes and resident lane
FMA/VRF work must pass independent traces. activity02 counts accepted private
FPU work, not occupancy. Native activity is reported with its documented
semantic-mask convention; no historical coverage percentage is reused.

Forced resident sets test-local validation/platform assertions. The separate
runtime-default arm has requested=0 and validated_available=0 and must retain
native selection with zero resident work. Neither arm advertises production
resident capability, board NORMAL_MEMORY eligibility, or default enablement.

rdcycle ROI includes query F32->F16, device query, Decode plan/group preflight,
workspace setup, packing for memory RVV, complete attention and final drain.
It excludes UART, gold/model checks and guard hashing. It is a complete SDK
two-head operator call, NOT a GGML token latency or whole-model result. Tensor
layout conversion outside this API, graph scheduling, cache lifecycle, context
locking/admission, Linux/device IO, model weights and other operators remain
outside. Model and host-capture time are never called accelerator timing.
No measured Resident benefit, FPGA validation or end-to-end improvement is
reported by this preparation-only handoff. Parent owns RTL protocol/image
checking and runtime/board admission remains gated with standard RVV fallback.

## Reproduction

The local login environment has LD_LIBRARY_PATH; preparation deliberately
rejects compiler environment injection. Use `env -u LD_LIBRARY_PATH python3 -B
.../attention_real/prepare.py --capture ... --heads 0,1 --output ...`.
All delivered executable plans and test receipts are collected by handoff.py
under the owned `operator_attention_real_prepare_20261115_*` prefix. No VCS,
hardware compile, SDK changes or git commits are part of this work.
