# Quantized KV Cache Layout Admission and Panel Gathering

## Why the earlier capture is not a runtime-layout proof

The historical capture graph explicitly calls `ggml_dup` on the permuted Q,
K and V operands before exporting them. The captured values are real model
values, but their materialized layout does not establish that the live KV cache
has the same strides. Do not change the capture or reclassify its numerical
checks as invalid: its scope is a materialized operand replay.

In the current llama.cpp `llama_kv_cache::get_k`, a token contains all KV
heads. After the Attention permutation, a D=128 Q8_0 example with two KV heads
has a 136-byte head stride and a 272-byte token stride. QBS row-major weights
cannot directly consume this as successive 136-byte K rows.

The original selector deliberately rejects that layout. Removing its equality
check alone would be incorrect: the descriptor has no weight-row stride field.

## Successor Implementation

Existing contiguous sources are sealed by running VCS experiments. Therefore
the new implementation uses separate `runtime_strided.c/.h` and
`selection_strided.h`; it does not alter their inputs or results.

- Selection preserves the original capability, mask, numerical-domain, alias,
  accessible-extent and head/token non-overlap checks. Only the contiguous-K
  restriction changes; admitted strided data must still be gathered.
- Each panel holds at most 32 K rows. At maximum D=256 and Q8_0, its capacity
  is `32 * (256 / 32) * 34 = 8704` bytes, independent of context length.
- Copy only visible K rows and their original quantized bytes. Do not decode,
  requantize or change block order during gathering.
- Reuse the panel for all M4/M2/M1 Query groups sharing its KV head. A new
  tile or KV head replaces it. Invalidate panel identity at every invocation;
  the KV cache can change between calls.
- Contiguous K retains the original direct descriptor path and copies no K.
- Reuse the original QBS descriptor/executor, Query quantizer, V decoder and
  per-head token-order online Softmax/PV schedule.
- Fallback is allowed only before callbacks/output writes. A failed command
  after execution starts remains an execution failure, not a fallback retry.

The extra storage is caller-owned software scratch, not an RTL SRAM addition.
`key_panels` counts gathered panels, and `key_bytes` counts copied payload
bytes. Neither counter measures DDR/AXI traffic or proves a speedup. The full
timer must include selection and panel copies when measuring deployment cost.

## Verification Scope

`test_native_strided.py` compares the successor with the original contiguous
execution using the independent QBS reference model. It covers Q4_0/Q8_0 K,
Q8_0 V, multiple head groups and token/tile tails, panel reuse, direct-path
zero-copy counters, rejection before execution, and command failure without
retry. GCC and Clang AddressSanitizer/UndefinedBehaviorSanitizer runs are host
contract checks, not native RTL execution or performance measurements.

The final host gate passes three tests: GCC execution, Clang ASan/UBSan
execution, and a negative mutation that removes invocation-level panel
invalidation. The mutation must fail specifically in the repeated single-panel
test. Each normal execution covers 288 layout/format/head/tail combinations,
plus a D=256 maximum-panel case and one padded, single-KV-head repeated panel.
The latter deliberately retains identical panel coordinates between calls while
changing K bytes, so a stale-cache implementation cannot pass by accidentally
missing on a different KV head.

The separate full-model run
`verification/out/akv-quantkv-model-live-20261024-01-control` generated the
same three greedy tokens in each baseline/candidate pair, but its independent
acceptance gate returned FAIL because candidate Decode used fallback instead
of native quantized Attention. Preserve the failed run and do not count
identical outputs under fallback as native coverage.
The trace must be segmented by generation step: `mapping=5` occurs during
four-token Prefill, which is intentionally outside this Decode-only adapter.
After TOKEN0, Decode reports `mapping=0 memory=1 runtime_called=1`, so its
mapping succeeds. Static analysis identifies the stricter K-row requirement as
an unavoidable later rejection; the old trace does not print selection reason.
Do not invent a second Decode shape bug from Prefill trace lines.

Before accepting this successor for deployment, additionally require:

1. Real GGML live-cache shape/stride mapping tests, including expected
   multi-token Prefill rejection and all supported Decode tensor views.
2. Native model-generation acceptance with command counts and no unexpected
   Decode fallback, using a fresh build and result directory.
3. Paired VCS measurements on identical strided inputs, including gathering
   cost, with the same decoder on both schedules for hardware attribution.
