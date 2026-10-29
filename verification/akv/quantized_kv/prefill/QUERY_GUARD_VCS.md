# Paired grouped-Prefill query-guard measurement

This experiment compares the current grouped Prefill execution path with the
same path using the isolated block-level nonfinite Query check. It does not
compare per-query execution with grouped execution.

## Construction

`query_guard_sources.py` derives a candidate admission function and executor
from canonical headers, reusing the original data structures and all execution
callbacks. Only the extra-query nonfinite check changes. The generated native
main keeps the existing real-capture output comparison, canaries, FCSR/VCSR
checks, command counts and ABBA ordering. Original and candidate functions are
in the same ELF and use the same scratch and output addresses.

`query_guard_build.py` rebuilds all 16 objects with the existing GNU recipes;
no old objects are reused. It verifies the captured tensor geometry and hashes,
changes only physical KV storage coordinates to the existing token-major test
layout, and checks native QBS execution and RVV V-decoding symbols. The first
build attempts retained a per-query-only symbol assertion from the older
experiment and were rejected after compilation. They were not simulated. The
successor checks `quant_prefill_native_qk`, which is actually required by both
grouped paths, instead of the intentionally unused `akv_quant_strided_execute`.

## Workload and invariants

- Real captured Qwen3 queries 16 through 19, head dimension 128, GQA=2.
- Q4_0 and Q8_0 K-cache cases; both use Q8_0 V-cache.
- Eight output rows, 1024 FP32 output elements per trial.
- Four native QBS commands and twenty V decodes in every trial.
- One gathered K panel in every trial: 1440 bytes for Q4_0 or 2720 for Q8_0.
- ABBA modes 0,1,1,0: original/candidate/candidate/original admission.
- ROI includes complete admission, grouped QK/Softmax/PV and output scatter.
- Output values are independently checked against the captured golden within
  the existing tolerance, and paired outputs must be bit-identical.

`query_guard_check.py` rejects the older per-query activity pattern and checks
all output words, flags, ordered trials, scope, layout and panel counts.
`test_query_guard_check.py` includes malformed/status/counter/output mutations.
`query_guard_run.py` verifies the reviewed SoC image and all source pins, runs
the protocol checker, then admits cycle results. No QEMU times are used.

This is a bounded real-data slice, not whole-model timing or proof of all
possible shapes. Promotion also requires fallback-boundary and runtime model
checks. Production software and RTL remain unchanged while these tests run.
