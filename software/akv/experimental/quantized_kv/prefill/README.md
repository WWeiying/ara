# Quantized Prefill Attention

This directory is the canonical shared C implementation used by the opt-in
llama.cpp/GGML RISC-V backend. It uses the existing QBS command interface and
ordinary RVV arithmetic; it adds no instruction or hardware resource.

`ggml_entry.h` is the C/C++ boundary. `ggml_entry.c` maps tensor metadata,
checks backend host allocations, then invokes whole-operation admission and
execution. The caller owns serialization, normal-memory/coherency assertions,
input lifetime and a private aligned workspace.

Supported requests use F32 queries, Q4_0 or Q8_0 keys, Q8_0 values, and per-query
FP16 masks consisting of a nonempty zero prefix followed by negative infinity.
The admission code is authoritative for shape, capability, alignment, extent,
alias and numerical-domain restrictions. Unsupported requests return fallback
before execution; failures after execution starts are terminal, not retryable.

Execution groups at most eight flattened query/head rows for one KV head.
Equal visible lengths share M4/M2/M1 QK commands without computing masked QK
positions. Values are decoded once per group/token, while every row retains its
original online softmax/PV token order. A bounded K panel handles supported
strided views; contiguous K views remain direct.

## Build and Dispatch

With the existing RVV, QBS, AKV and quantized-KV build settings enabled, add:

```text
GGML_RISCV_AKV_QUANT_PREFILL=ON
```

The reviewed CMake integration defaults its Prefill directory to this directory,
derived from `GGML_RISCV_AKV_RUNTIME_DIR`. An explicit
`GGML_RISCV_AKV_PREFILL_DIR` remains available for compatibility. Neither the
default sources nor their kernel headers depend on the verification tree.

Runtime selection still requires the existing quantized-KV/normal-memory opt-ins
and `GGML_RISCV_AKV_QUANT_PREFILL=1`. Single-query Decode remains on the original
Decode path. The feature defaults OFF; general RVV fallbacks remain available.

The verification directory contains only compatibility includes for these eight
files, tests, probes and independent experiments. Do not maintain a second
execution implementation there. Relocation changes organization, not arithmetic
or performance; numerical and model checks must continue to use this shared code.
