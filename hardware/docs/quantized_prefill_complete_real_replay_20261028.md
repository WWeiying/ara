# Real-data acceptance of the composed Prefill call

## Scope

This test connects whole-operation admission and the complete experimental
execution entry to the actual GGML Query quantizer, Q8_0 value decoder and
vector helpers. QK commands execute through the QBS numerical reference.
It is host functional evidence, not native RTL execution or timing.

Input is the captured Qwen3-1.7B-Q4_K_M layer-0 Prefill: 20 query tokens,
16 query heads, eight KV heads, D=128 and causal prefixes 1..20. For each K
format, the captured contiguous input and a derived layout with eight padding
bytes per K row are both checked. Padding changes layout only; every actual
quantized block remains unchanged. V remains captured Q8_0.

## Results

| K format | K layout | Checked outputs | QBS reference commands | Completed groups | V decodes | K bytes gathered | Maximum absolute GGML golden error |
|---|---|---:|---:|---:|---:|---:|---:|
| Q4_0 | Captured contiguous | 40,960 | 160 | 40 | 480 | 0 | 1.40815973e-6 |
| Q4_0 | Eight-byte row padding | 40,960 | 160 | 40 | 480 | 34,560 | 1.40815973e-6 |
| Q8_0 | Captured contiguous | 40,960 | 160 | 40 | 480 | 0 | 2.95042992e-6 |
| Q8_0 | Eight-byte row padding | 40,960 | 160 | 40 | 480 | 65,280 | 2.95042992e-6 |

Every result is bit-exact against execution of the existing per-query QBS
Decode implementation on the same data, and the host floating-point exception
flags agree. Query quantization executes once for each of the 320 query/head
rows. The independent captured-GGML check uses the unchanged preselected
`2e-5 + 2e-5 * abs(golden)` tolerance.

These errors are not the earlier 5.96e-8 GGML-dot replay errors: this test
uses QBS numerical dot-product semantics instead of the host GGML dot helper.
The scheduler adds no difference relative to the per-query QBS reference.
Neither comparison establishes native hardware behavior; the VCS test is a
separate required gate.

## Reproduction and evidence

```sh
python3 verification/akv/quantized_kv/prefill/run_execute_replay.py \
  verification/out/prefill-execute-real-NEW
```

Accepted run: `verification/out/prefill-execute-real-20261028-03`.
The runner verifies the capture audit, hashes compile dependencies and compiler
frontends, stores commands/logs, verifies inputs again after execution, and
records the binary hash and scope in `result.json`.

The first two attempts failed during build setup (a missing quantizer
declaration and the baseline runtime object missing from the link). They did
not execute numerical tests; their directories remain separate. Fixes added
the actual GGML declaration header and the existing runtime object, without
changing kernels or tolerances.

Production dispatch remains unchanged. Before enabling this path, the full
engine's admission/preparation/output costs and native behavior still need
measurement, followed by GGML integration and model-level acceptance.
