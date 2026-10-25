# Quantized Attention fixed-size field copies

## Scope

The previous three-call retirement diagnostic found frequent out-of-line
`memcpy` calls for 2/4-byte admission fields and Q8_0 value scales. This change
uses explicit compiler builtins for those object-representation copies under
GCC/Clang, including builds using `-fno-builtin`. Other compilers retain ordinary
`memcpy`. This is a software optimization, not an RTL or ISA change.

Changed shared headers cover contiguous/strided admission, GGML parameter
mapping, online scale validation, and RVV Q8_0 V scale decoding. The bulk
K-panel gather in `runtime_strided.c` is unchanged. No checks are removed:
bounds, layouts, finite values, mask prefix, capability and fallback remain
identical. No typed-pointer punning, assumed alignment, floating arithmetic
reassociation, or new FP conversion is introduced.

## Validation

Run from the worktree root:

```sh
python3 -B -m unittest discover -s verification/akv/quantized_kv -p test_field_copy.py -v
python3 -B -m unittest discover -s verification/akv/quantized_kv -p test_selection.py -v
python3 -B -m unittest discover -s verification/akv/quantized_kv/strided_selection -p test_selection.py -v
python3 -B -m unittest discover -s verification/akv/quantized_kv -p test_online.py -v
python3 -B -m unittest discover -s verification/akv/quantized_kv -p test_ggml_decode.py -v
```

All 17 tests passed on 2026-10-25. Included evidence:

- All 65,536 16-bit patterns at eight byte offsets; selected F32 signed zeros,
  subnormal/normal boundaries, infinities and quiet/signaling NaN encodings.
- Bit preservation, unchanged floating flags and guard-page boundary reads.
- Host GCC and Clang ASan/UBSan; C++ backend header compatibility.
- Admission tests: 8,195 accepted, 65 rejected and 32,768 view cases.
- Strided boundary/rejection tests and genuine Q4_0/Q8_0 captured model data.
- 320 online scheduling cases with exact operation order and output guards.
- GGML mapping: 2,048 accepted, 23 rejected, 13 deferred cases and real captures.
- Actual GNU RISC-V object check with `-O2 -fno-builtin -mstrict-align`:
  admission and RVV V decoder have no undefined `memcpy` reference; unknown-
  alignment scalar reads compile into byte loads. Old-expression control
  still has an external `memcpy` reference under identical flags.

The strided-selector source identity was updated alongside its current parity
test. Historical run receipts and pinned snapshots are unchanged; their hashes
and measured timings continue to describe the previous version only.

No new RTL timing result, whole-model speedup, VCS regression, synthesis or
FPGA result is claimed. The standalone llama.cpp checkout was not modified;
consumers must rebuild against these shared headers to use the optimization.
