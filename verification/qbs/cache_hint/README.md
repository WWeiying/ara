# Prepared-cache hint-first experiment

## Purpose

The production prepared-activation cache searches entries in slot order. A
per-M4-group slot hint can prioritize the previously matched entry without
changing cache identity. A hint is never sufficient for a hit: the key, input
and output sizes, and every input byte must still match. On a mismatch the
candidate scans every remaining slot. Equal inputs from different groups can
still share an entry. Replacement, allocation failure and payload/FFLAGS
conflict handling are unchanged.

`prepare.py` derives a candidate from the installed source using unique textual
anchors and records hashes. It does not patch the installed runtime. The
optional hint is caller-owned; stale and out-of-range hints are safe. Runtime
integration would need eight hints per worker, not a new group field in the
semantic key.

## Verified so far

Run from the signoff worktree:

```sh
python3 verification/qbs/cache_hint/run_host.py \
  --cxx /usr/bin/clang++ \
  --captures /home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/prefill/operators \
  --runtime /home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv \
  --output verification/out/cache-hint-host-NEW
```

The output directory must be new. Results, commands, source hashes and logs are
retained together. `result.json` is only written after both executables pass and
all recorded source hashes remain unchanged. Assertions must remain enabled.

The accepted host run is `verification/out/cache-hint-host-20261029-02`:

- AddressSanitizer and UndefinedBehaviorSanitizer enabled; no diagnostics.
- 10,000 deterministic randomized operations, 4,330 paired get/put checks.
- Explicit stale, invalid and wrong hints; cross-group duplicate inputs;
  replacement; allocation failure; clear; payload and FFLAGS conflict cases.
- Captured layer-0 inputs replayed in Q, V, K, Attention-output, FFN-gate,
  FFN-up, FFN-down order. Each has 15 rows; only the three complete M4 groups
  participate. The three tail rows are outside this cache optimization.
- Paired outputs, hit/miss decisions, flags, replacement statistics, payload
  copies, retained bytes and destination canaries agree.

| Host replay total | Original | Hint-first |
|---|---:|---:|
| Queries | 21 | 21 |
| Hits | 9 | 9 |
| Misses | 12 | 12 |
| Requested comparison bytes | 2457600 | 1990656 |

The K=8960 FFN-down groups exceed the cache entry-size limit in both variants;
they remain misses with stores rejected. This is not newly supported caching.

The earlier `cache-hint-host-20261029-01` failed during GCC sanitizer linking
because the system `libasan.so.6.0.0` was unavailable. It did not run tests and
is not counted as a passing result. Clang here is the system x86 compiler, not
ZCC and not the RISC-V performance toolchain.

## Evidence boundaries

`replay.cpp` uses real activation bytes as exact-match keys but deterministic
opaque payloads. It checks cache behavior, not quantizer numerical correctness.
It is a controlled cache replay, not a reconstruction of graph lifetime or
multiworker scheduling. It neither replaces the already accepted model checks
nor establishes production equivalence for a future integrated implementation.

Requested comparison lengths are not memory traffic. The production RVV byte
helper uses e8/m8 chunks and exits at the first mismatching chunk. At VLEN=1024
that chunk can be 1024 bytes, whereas successful equality checks must consume
the whole input. A 19% decrease in requested lengths therefore does not imply
a 19% time reduction. This experiment has no measured speedup.

## Next acceptance gates

1. Build a paired RISC-V benchmark from the complete captured M4 groups. Include
   quantization, hint maintenance, lookup, copy, flags and cleanup in the ROI;
   compare full payloads and architectural flags against direct preparation.
2. Run the same ELF on the accepted VCS image with bounded duration and ABBA
   ordering. Retain ordinary single-group and cache-miss controls. Do not
   promote a change that only improves requested-byte counters.
3. If cycles improve reproducibly, integrate hints into the worker-local
   prepared-cache state without changing eligibility or fallback. Recheck
   paired model logits, token choices, graph schedule and native command trace.

No production software, RTL, default switches or model dispatch policy has
been changed by this experiment.
