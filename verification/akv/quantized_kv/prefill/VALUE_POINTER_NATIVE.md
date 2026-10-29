# Native pointer candidate preparation

`value_pointer_build.py` reuses the fresh-object native build recipe and
changes only its source generator. It rebuilds all sixteen objects, rechecks
the real capture hashes and tensor geometry, and records the pointer generator
and wrapper in the source pins. It does not edit sealed copy-experiment files.

The generated program compares original grouped Prefill against direct cached
V-row consumption, with real Qwen3 queries 0..7, GQA=2, D=128, one selected KV
head from the eight-head token-major layout. Both paths execute eight QBS
commands and 72 PV updates; expected decode counts are 12 and 8. The same
ABBA program verifies all 2,048 outputs per trial and sticky FCSR/VCSR state.

Native build metadata must contain `value_pointer: true`. Do not infer the
variant from the generic `VCACHE` UART prefix or reuse copy results as pointer
results. A valid build alone is not functional or performance acceptance.

## Preserved build rejection

`verification/out/value-pointer-q4-build-20261029-01` compiled and linked, but
its initial variant audit rejected the missing standalone `vptr_value` symbol.
Inspection showed the compiler inlined that getter into the execution path;
only `vcache_qk` remained as an out-of-line candidate callback. This was an
overly restrictive audit, not an RTL or arithmetic failure. The original
attempt is retained and must not be submitted for simulation: its generic
build report predates successful pointer-variant admission.

The successor verifies the generated pointer scheduler connection and getter
source, records whether the standalone getter survived compilation, and marks
a variant-audit failure explicitly. Source inspection establishes absence of
explicit V-row copies; it does not label an absent symbol as proof of zero
machine-level memory traffic. Performance remains a VCS measurement question.
