# Shared GGML Q8_K M4 preparation

`q8_K-m4.h` is the canonical helper for the accepted Q8_K M4 activation
preparation algorithm. Install the identical header into GGML's
`ggml/src/ggml-cpu/arch/riscv/` directory and apply `repack-q8k-m4.patch` at the
llama.cpp root. The patch assumes the existing QBS/Q8_0 M4 integration is present.
It changes only one include and Q8_K M4 specialization selection, not the
generic oracle, weight layout, matrix kernels or existing Q8_0 implementation.

```bash
cp software/qbs/ggml/q8_K-m4.h \
  /path/to/llama.cpp/ggml/src/ggml-cpu/arch/riscv/q8_K-m4.h
git -C /path/to/llama.cpp apply \
  /path/to/ara/software/qbs/ggml/repack-q8k-m4.patch
```

The current local runtime copy is under `/home/wangwy/llama/llama.cpp`; it is
modified but is not committed/pushed by this integration. The reversible patch
and canonical header are tracked in this repository so the exact change is not
lost in an external dirty tree.

## Selection and numerical contract

- Default remains generic. `GGML_RISCV_QBS_M4_PREPARE=1` opts into the Q8_0 and
  Q8_K M4 preparation paths in the tested QBS/no-Zvfh GGML build. Zvfh and other
  build paths retain their existing selection. Extending that build policy is
  separate from the helper's VLA correctness.
- `GGML_RISCV_QBS_TRACE_M4_PREPARE=1` enables per-call dispatch traces, including
  `GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=... path=rvv|generic k=...`.
- Four contiguous rows, K divisible by 256, and nonoverlapping input/output are
  required, as in the existing generic entry. Unsupported rounding modes or
  conservative input-domain rejection fall back before any output write.
- Integer-only VLA preflight rejects subnormals/nonfinite values and unsafe
  nonzero magnitude ranges without changing FP flags. It preserves accumulated
  vector tails when strip mining. Quantization preserves first signed maximum
  on ties, explicit fused rounding, interleaved bytes and sixteen-element sums.
- Fast-math/non-RVV builds use the generic helper rather than trying to compile
  unsupported intrinsics. The numerical contract is tied to the tested GNU
  production generic; changing compiler/libm requires requalification.

`test_q8k_canonical.py` verifies that the canonical vector/preflight function
bodies are token-identical to the accepted candidates, except for comments and
the outer build/fallback guard, and that the installed header matches exactly.
Old isolated headers are frozen historical test inputs, not a second active
implementation to tune independently.

## Evidence

The accepted VLA implementation gives 1.131934x speedup for a real complete
M4/N1536/K1536 projection on RTL, including activation preparation. Preparation
alone improves 1.362240x. The receipt is
`verification/qbs/results/q8k-full-projection-vla-20261023.json`; neither number
is full-model speedup.

Private full-TU numerical checks cover 12000 observations at VLEN128/1024,
including six real activation captures and FP/status boundaries. The canonical
live-TU graph gate recompiles the actual runtime source, with no privately
rewritten selector or observer, then links the accepted independent graph
stimuli and scalar oracle. Its OFF/ON output/status/dispatch results are a
separate acceptance requirement; see `verification/qbs/Q8K_PRODUCTION_CANDIDATE.md`.
