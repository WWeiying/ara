# Ordered RVV square sum for fused GGML RMSNorm

This is an isolated experiment, not an enabled production backend. It adds no
RTL or instruction and makes no measured area claim. The candidate uses the
existing RVV FP32 multiply and ordered FP64 widening-reduction instructions.

## Computation and numerical contract

The accepted GGML fused RMSNorm first computes:

```c
double sum = 0.0;
for (int64_t i = 0; i < width; ++i)
    sum += (double)(x[i] * x[i]);
```

The product rounds in FP32 before conversion to FP64. `rms_sum.h` preserves
this distinction: vector FP32 multiply, followed by `vfwredosum`, carrying the
FP64 seed across strips in original element order. It does not use unordered
reduction, FP32 accumulation or widening multiplication. The original division
to mean, FP32 rounding, square root, reciprocal and two output multiplies remain
unchanged, as does the fused norm/weight-multiply path.

The experiment assumes stable, ordinary valid input memory, entry `vstart=0`
and no observer of intermediate exception timing. Batched loads/products do not
preserve the timing/order of individual memory faults or intermediate `fflags`.
This is not an MMIO transformation. Production runtime/board admission and
model-level validation remain separate requirements.

The loop uses dynamic VL rather than a fixed VLEN, but the current target
experiment is four lanes and VLEN=1024. Do not call other VLEN configurations
tested merely because the source is vector-length agnostic.

## Actual inputs and baseline

The first four Qwen3 prompt token IDs are 32, 4621, 17654 and 51435. The first
Decode token is 22406 after the same real 40-token Prefill. Only these five
embedding rows are dequantized from the hash-bound Qwen3-1.7B Q4_K_M GGUF;
`blk.0.attn_norm.weight` and the RMS epsilon come from that same file. These are
reconstructed inputs, not captured raw tensors.

Before target execution, the complete original fused GGML function is compiled
and its 10,240 outputs compared byte-for-byte with the previously captured
Prefill/Decode normalized activations. This gate passed. The source group and
shape helper are extracted unchanged from the accepted sources. The candidate
changes only the square-sum loop; it does not replace GGML with an artificially
weak scalar implementation or disable fusion.

## Target experiment and completion

The ELF contains original/candidate kernels and uses ABBA for both the actual
single-row Decode input and four-row Prefill input. All 40,960 timed-call output
elements, canaries, final FCSR/VCSR/vstart are checked. Separate strict-math
objects test 53 width/IEEE cases across all five legal rounding modes, including
NaNs, infinities and subnormals. Ten raw-FP64 sum comparisons use order-sensitive
large/small values: comparing only final FP32 norm output could hide a changed
FP64 accumulation order. Boundary cases do not contribute performance claims.

The completed caller reads VCSR, FCSR and vstart before the final fenced cycle
read. In the audited SoC, vector CSR service waits for the backend to become
idle; a normal store keeps its instruction running until its B response. Thus
the end is not simply the scalar function-return/last-command-issue time. The
reported interval includes these completion reads; no assumed constant is
subtracted. A successor recompiles only this caller and reuses the sealed
arithmetic objects, preserving the original build and avoiding full rebuilds.

The checker also requires 288 actual ordered-widening-reduction allocations in
the vector trace, the expected hardware configuration and an independent
protocol PASS. Performance improvement is not a condition for functional PASS.
No candidate is promoted on host replay, disassembly or launch alone.

The experiment tools are in
`verification/performance/end_to_end_baseline/` (`prepare_rms_norm_data.py`,
`build_rms_norm_native.py`, `build_rms_norm_completion.py`,
`rms_norm_campaign.py` and `collect_rms_norm.py`). All outputs live in fresh
directories of the sole verification worktree. No full model is rerun merely to
recapture inputs already covered by the accepted evidence.
