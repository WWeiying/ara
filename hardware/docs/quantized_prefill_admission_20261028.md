# Whole-operation admission before Prefill execution

`verification/akv/quantized_kv/prefill/admission.h` is an experimental selector,
not a production backend entry point. Its purpose is to rule out fallback
conditions across the complete operation before any query quantization,
command submission or output write occurs.

## Checks and cost

- Validate complete Query/output views, accessible byte extents, stride
  arithmetic and non-overlap, not only the first row's addresses.
- Validate every mask row as a nonempty visible prefix followed by negative
  infinity. Prefix lengths need not be monotonic; holes, nonbinary mask values
  and entirely masked rows fall back.
- Select the row with the largest visible prefix and reuse the existing
  strided Decode selector on that row. This checks the device contract,
  layouts, finite KV scales across the visible union and that query row.
- Check all other query rows using the same bitwise nonfinite and quantizer
  range rules. This avoids rescanning the full visible KV range per query.
- Check the larger command/result capacity required by cross-query grouping.
  A device capable of the original two-head Decode is not assumed to support
  a four-row command. The current bridge admits activation base alignment
  requirements up to four bytes; stronger requirements conservatively fall back.
- Copy the completed plan to the caller only on success. Failure preserves the
  plan and output and does not change floating-point exception flags.

The initial software bounds are 256 query rows, D divisible by 32 and at most
256, and the existing Decode restrictions on formats, KV/head sizes, rounding
state, capabilities, optional features and view layouts. This is not a claim
that every model or Attention variant is admitted. In particular, arbitrary
mask holes, attention sinks, bias and softcap are not newly supported.

Caller responsibilities remain accessible input storage, immutability through
execution, serialized use, and a separate result-plan allocation. Execution
workspace aliasing and the final GGML metadata bridge still need their own
whole-call checks before production integration.

## Evidence

```sh
python3 verification/akv/quantized_kv/prefill/test_admission.py
```

Twenty directed cases pass with GCC and Clang UBSan. They cover mixed
head-major/token-major views, a maximum-prefix row that is not the last query,
bad extents and mask rows, aliasing, a late query's signaling NaN, tiny query
range, nonfinite KV scales, hidden KV rows, disabled mode, unsupported state,
and insufficient M/result capacity. Rejection preserves the plan, output and
a preexisting floating-point exception flag.

The additional `admit_capture.c` replay passed both real Qwen3 captured formats
(Q4_0/Q8_0 keys with Q8_0 values), checking 20 query tokens, 16 query heads,
8 KV heads and D=128. It verifies prefixes 1..20 and issues no commands.

This admission result is not numerical execution or performance evidence.
The independent native VCS ABBA experiment remains the timing gate; production
dispatch is unchanged while that experiment runs.
