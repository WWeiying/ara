# Actual-runtime exponential replay

This closes the behavioral part of the Newlib/Linux math-library discrepancy
found during Attention attribution. It does not measure Linux hardware cycles
and does not change SDK, GGML, mathematical policy, RTL or default selection.

## Real data, not synthetic exponent arguments

`../grouped_pv/attribution/extract_exp.py` consumes only the exact accepted
retirement result. The linked ELF validates instruction bytes and GNU operands.
The extractor tracks NaN-boxed `fa0` writes, records the value on entry to the
actual `expf` symbol, and records the returned value at that function's `ret`.
FP stores are reads of `fa0`, not updates. All four ABBA calls must contain 768
complete exponent invocations and identical ordered input/result pairs.

```sh
python3 verification/akv/quantized_kv/grouped_pv/attribution/extract_exp.py \
  --run verification/out/attention-retirement-vcs-20261027-01 \
  --output verification/out/NEW_EXP_PAIRS
```

Accepted extraction: `verification/out/attention-exp-pairs-20261027-01`.
There are 762 distinct input bit patterns, six negative infinities, and finite
arguments from -151.5380859375 to -0.0465087890625. Forty-four finite inputs are
below -80. The original bytes are Newlib results, not a universal libm golden.

## Normal Linux library execution

```sh
python3 verification/akv/quantized_kv/math_runtime/run_linux.py \
  --pairs verification/out/NEW_EXP_PAIRS/exp-pairs.json \
  --output verification/out/NEW_LINUX_REPLAY
```

The probe uses the normal GNU Linux compiler and actual static libm, with
strict FP compilation and builtin replacement disabled. A volatile function
pointer forces real public `expf` calls. The link map must include
`libm.a(e_expf.o)`. The pinned archive is the one selected by the toolchain
used for the normal-library llama.cpp model. QEMU boots the existing minimal
Linux environment and executes the full 768-argument probe; no custom QBS
instruction or RTL timing is involved.

For every call the probe resets FCSR to RNE with clear flags, presets errno,
then records result bits, flags and errno. Negative-infinity behavior is
checked separately. Outputs must be in [0,1], flags must not include invalid,
divide-by-zero or overflow, and errno must be unchanged or ERANGE. Every output
is compared against Python binary64 exp rounded to binary32 within one ULP.
That reference is diagnostic, not a universal correctly-rounded expf proof.
No existing Attention tolerance is changed by this separate probe.

## Accepted result

`verification/out/attention-linux-exp-replay-20261027-01/result.json` is PASS:

| Item | Result |
| --- | ---: |
| Actual arguments replayed | 768 |
| Linux versus recorded Newlib differing outputs | 88 |
| Maximum Linux/Newlib distance | 1 ULP |
| Maximum Linux/diagnostic-reference distance | 0 ULP |
| Calls raising underflow | 37 |
| Calls setting ERANGE | 25 |

These differences are not evidence of an RTL bug. Different valid libm
implementations need not return identical final bits. Zero observed diagnostic
reference error on this set is not proof of greater quality for every input.
The Linux and bare-metal benchmark must not share an assumed identical libm
golden when their actual code differs.

## Implementation consequence

The Linux exponent object depends on `__exp2f_data` and the three error helpers
`__math_may_uflowf`, `__math_uflowf` and `__math_oflowf`. Its error-helper object
uses TLS errno relocations. Therefore simply extracting an object and stubbing
these functions in bare-metal VCS is not a faithful replacement. Real inputs
exercise underflow/error behavior; assuming every input is a harmless normal
number would miss observed calls. Do not zero flags, clip arguments or remove
error paths to make a benchmark appear faster.

A future runtime-aligned RTL measurement needs correct single-thread TLS/libm
support or a separately reviewed portable math implementation with an explicit
contract. Until then, do not project the 42.2% bare-metal exponential instruction
fraction onto the complete Linux model, or select new exponential hardware from
that fraction alone. Existing paired results remain valid within their stated
same-library scope.

Four extractor tests and four replay-checker tests pass on 2026-10-27. They
cover argument boxing, stores versus writes, missing/mismatched calls,
complete dataset/order, changed input/state, large error and negative infinity.
Source, tool, archive, kernel, initramfs, executable and output hashes are retained.
