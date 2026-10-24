# Full-Workload V Decode: Faster Verification Harness

## Why The Harness Changed

The original VCS run is retained at
`verification/out/akv-quantkv-value-decode-20261024-01`.
Its first original-decoder trial completed with 416,591 timed cycles and hash
`4df2ae0e8ad145b8`, matching the independent host byte-hash oracle. This is a
partial observation, not a completed eight-trial acceptance or a speedup result.

In its cycle trace, the end-of-kernel drain was at cycle 978,885 and the next
trial's pre-kernel drain was at 3,856,682. The intervening 2,877,797 cycles include
checking, UART output and next-trial setup. The old checker hashes all four
bytes of each F32 word with four 64-bit multiplies, on every trial. It also passes
each F32 through a raw-bit helper. This measured off-timer cost motivates a
successor harness, not a change to the arithmetic kernel or test dimensions.

## Preserved Work And Checks

- The same two original real-model V captures, both KV heads, all 128 visible
  tokens per head, D128, and 32,768 output words per trial.
- Original/candidate/candidate/original for each capture: eight trials and
  262,144 output words total. Capacity rows 128--255 remain outside the domain.
- The original production scalar decoder and unchanged RVV candidate source.
  The successor includes `value_decode_main.c` under a renamed, dead old main;
  the linker removes that old main. No production source is copied or rewritten.
- All 3,584 directed finite-scale/signed-byte boundary outputs.
- Per-trial guards, every output word, FCSR=0, VCSR=5 and scalar equality against
  the first original trial. The checker is compiled with auto-vectorization off;
  it is not an RVV equality test that might share the candidate's error.
- The timed row traversal and drain remain the same. Guard initialization,
  comparison, checksum and printing are outside the timer. Code layout can
  nevertheless affect cycle counts: report the new ABBA experiment separately,
  not by mixing old partial timings with new candidate timings.

## Explicit Checksum Contract

The first original trial stores an immutable reference array. Each later trial
is compared word by word against it. After all four trials of one capture, the
reference is hashed once and checked independently against the original bytes
on the host. Thus the independent reference check covers all later outputs
through exact scalar comparisons, without repeatedly hashing identical data.

This checksum is named **word_fnv64**, not the old byte-wise FNV checksum:

```text
h = 14695981039346656037
for each F32 output word, in head/token/dimension order:
    h = ((h XOR uint32_bits(output)) * 1099511628211) modulo 2^64
```

It is a noncryptographic digest, not a complete host output dump. Both versions
have finite collision risk; the successor keeps complete on-target per-word
comparisons. The host reconstructs finite F16 scale times signed INT8 exactly,
including signed zero. Nonfinite visible scales are rejected.

The parser rejects missing/reordered/duplicate trials or hashes, wrong hash
version, any mismatched word count, exception flags, guard error, malformed
records, failed assertions, nonzero UVM summaries and premature termination.
The worker additionally checks the accepted simulator, ELF/source/capture pins,
image-memory contract, independent backend/AXI protocol evidence, simulator exit
and post-run source identity. Functional acceptance does not require a speedup.

## Files And Execution

- `value_decode_fast_main.c`: successor harness, unchanged included kernels.
- `build_value_decode_fast.py`: reuses the original data/decoder objects and
  changes only the main object; independent build and source receipts.
- `check_value_decode_fast.py`: independent word-format oracle and parser.
- `run_value_decode_fast.py`: direct-owned VCS execution and strict acceptance.
- `test_value_decode_fast.py`, `test_value_decode_fast_run.py`: format,
  transcript mutation, build-gate and acceptance-path tests.

Use a fresh output directory for every invocation. The execution bound remains
three hours; timeout or interruption is not a numerical failure or a PASS.
No RTL, QBS descriptor, Attention schedule, tolerance, GGML default selection,
or running full-Attention experiment is changed by this harness.
