# Quantized Prefill: Source-Based Follow-Up

This is a proposed follow-up, not an implemented optimization or a measured
Prefill performance claim. No running runtime or RTL source was changed.

## Current Restriction

`software/akv/experimental/quantized_kv/ggml_decode.h` requires one query
token and one output token. `selection.h` repeats the requirement. The online
state in `online.h` indexes rows by query head; one visible-token count is
shared by the whole group. A Prefill call instead has multiple query tokens,
each with its own causal visible prefix. Removing the mapper check alone
would therefore change semantics or use incorrect addresses/masks.

The current quantized route uses QBS for grouped QK and ordinary RVV/software
for value decode, online softmax and accumulation. It is separate from the
native AKV descriptor path. The hardware already has useful matrix resources;
a new instruction is not justified just by this mapper restriction.

## Why a Row Loop Is Not the Performance Design

Calling the Decode entrypoint for every query could establish a correctness
reference, after validating the whole operation before any output write.
It would also repeat significant work:

- `akv_quant_select` scans the visible K and V block scales for nonfinite data
  on each invocation, as well as checking masks and query values.
- `akv_quant_strided_execute_impl` resets `panel_valid` at each invocation.
  A strided K tile would be gathered again for each query token.
- `akv_quant_online_shared` decodes V once per token for the query-head group,
  but the outer query loop would decode it again for each query token.

Thus a row loop is useful as an oracle, not sufficient evidence of an efficient
Prefill implementation. No speedup is inferred from reduced fallback counts.

## Proposed Bounded Schedule

1. Admit the complete tensor operation, including buffer extents, aliasing,
   masks, query ranges and visible K/V scales, before modifying any output.
   Never use pointers alone as evidence that a previous data scan is reusable.
2. Form a bounded group of `(query token, query head)` rows belonging to one
   KV head. Reuse existing QBS M4/M2/M1 commands for QK; retain each row's
   individual causal prefix instead of a single group-wide prefix.
3. Gather each K tile once for that group. Decode each required V token once,
   then update only rows for which the token is visible. Preserve each row's
   increasing-token arithmetic order and existing scalar exponential behavior.
4. Keep independent maximum/sum/output state for every active row. Bound group
   size and scratch space rather than allocating a full score matrix. Account
   for longer-lived output accumulators and resulting register/cache pressure.
5. Reject unsupported masks, sinks, bias, softcap, layouts or worker ownership
   before execution. After native work or output initialization begins, errors
   must remain terminal, not silently rerun fallback on partially written data.

This increases software reuse without changing the RVV/QBS architectural
contract. It may still lose on short prompts or tiny groups; dispatch thresholds
must follow complete-call measurements, not an assumed advantage.

## Evidence Required Before Promotion

- Real captured Prefill Q/K/V and masks, including existing-prefix plus prompt,
  a partial final group, and query groups crossing causal tile boundaries.
- Compare against the original GGML path and a row-by-row reference. Check
  every output, guards, caller state, and masked rows not read or executed.
- Test multiple GQA ratios, D, context lengths, Q4_0/Q8_0 K and Q8_0 V, with
  unsupported cases proving unchanged fallback and no partial output writes.
- Run one bounded representative VCS complete-call comparison first. Include
  admission, gathering, quantization, QK, softmax/PV and final writeback.
  Record actual K panels, V decodes and native work; do not extrapolate the
  bare-metal Newlib exponential cost to the Linux runtime's different libm.
- Integrate only after a reproducible benefit; then verify real model execution
  using normal libraries. Keep the existing Decode path unchanged initially.
