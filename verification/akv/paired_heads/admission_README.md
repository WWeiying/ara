# Stateless paired-head admission preparation

`software/akv/experimental/paired_heads/admission.h` separates capability/shape
selection from the single-thread benchmark's mutable global switches. It is a
pure helper only: production native code and the sealed running benchmarks do
not yet call it. The caller must first validate its complete plan, obtain
capabilities before FULL, and retain the normal context ownership protocol.

The helper accepts only explicit request 1, F16, 2--8 actual heads and
D64/96/128. D128/GQA6 remains assigned to the existing six-head specialization.
Token-axis activation, row/tail/PANEL4, 64-token tile, context and dimension
capabilities are required. Missing D-axis-tail support rejects D96 rather than
using D128 support as a substitute. Odd heads are admitted for a subsequent
pair-loop plus original generic tail; this test does not execute that loop.

```sh
gcc -std=c11 -Wall -Wextra -Werror -O2 \
  verification/akv/paired_heads/test_admission.c \
  -o /tmp/akv-pair-admission
/tmp/akv-pair-admission
```

Actual host result on 2026-10-24: `PAIR_ADMISSION_PASS assertions=100620
production_integrated=0`. The independent expected policy exhausts dimensions
0--257, heads 0--9, max-head capacities 0--9, format values 0--3, all eight
dimension-capability combinations, each mandatory capability absent, null
inputs, request OFF/invalid and interleaved selections. Assertions stay enabled.
This is policy testing, not RTL, numerical, concurrency or GGML acceptance.

A separate GCC AddressSanitizer/UndefinedBehaviorSanitizer build was attempted
but could not link: host `libasan.so.6.0.0` and `libubsan.so.1.0.0` were missing.
No sanitizer execution or PASS is claimed. Do not change the system toolchain
or install packages merely to turn that optional check green.

## Decode dispatch preparation

`dispatch.h` provides the corresponding immutable-call QK and PV loops. It
does not replace the sealed benchmark or canonical native functions. Admission
must be computed once before FULL and passed to these loops by the future
caller. A disabled call forwards the whole group to the original generic
helper. An enabled call forwards pairs to the existing measured assembly and
an odd final head to the original generic helper. There is no allocation or
mutable process-wide state. Existing D128/GQA6 dispatch must remain outside
these generic loops.

```sh
python3 -B verification/akv/paired_heads/test_dispatch.py
```

Actual host routing result: 24576 schedules passed across D64/96/128, 1--8
heads, every token count 1--64, four Query strides including a non-cacheline
stride, and enabled/disabled calls. The test checks each leaf's address,
dimension, token count, head coverage and call count. Seven intentional
mutations of Query/score/accumulator/scale offsets, pair advancement, odd-tail
handling and forced-generic selection must be rejected. Leaf functions are
stubs: these checks do **not** establish numerical correctness or actual
odd-head RTL acceptance. They prevent pointer/dispatch regressions before that
more expensive gate.
