# Stateless native-runtime candidate

This is the next integration candidate, not the single-thread `native_bench.c`
wrapper. It generates a successor C translation unit from the canonical source
with four exact, unambiguous substitutions and compiles a fresh GNU RV64 object.
The original native source is neither overwritten nor edited while its pinned
KV256/F32 consumers execute.

```sh
python3 -B -m unittest discover -s verification/akv/paired_heads \
  -p test_native_candidate.py -v
python3 -B verification/akv/paired_heads/prepare_native_candidate.py \
  --output <FRESH_CANDIDATE_DIRECTORY>
```

Recorded preparation: `verification/out/akv-paired-native-candidate-20261024-01`,
`CANDIDATE_COMPILED_NOT_EXECUTED`. Two host transform tests passed. The emitted
`candidate.patch` contains exactly one include, one call-local selection before
FULL, and two generic Decode call replacements. Prefill and segmented D256
remain unchanged. Existing GQA6 branches still bypass the generic dispatch.

`AKV_PAIR_HEADS=1` explicitly requests the candidate; missing/other values mean
OFF. A freestanding target without getenv stays OFF. Selection checks VLEN1024
and actual capabilities once per complete call, before its first FULL. Its
result is a local variable, not process-wide mutable state. QK/PV dispatch
uses the reviewed pair leaves and the original generic odd-head tail. The
existing full-context GGML mutex remains required; stateless selection alone
does not make the one-context hardware concurrently usable.

The candidate object contains the actual runtime entry points and references
both pair leaves. It contains no benchmark mutable switches. Its object build
is not a link, native numerical test or deployment acceptance. Before promotion:

1. Complete the currently pinned KV256 gate without source drift.
2. Link this candidate with the same assembly used by the accepted experiments.
3. Check actual even/odd-head complete calls, per-call OFF/ON interleaving,
   missing capabilities, six-head specialization and default OFF.
4. Re-run matched complete-operator timing including actual selection costs.
5. Update the shared runtime/CMake only after the exact candidate passes; keep
   GGML selection, error propagation and original fallback intact.

This avoids a permanent copy of the full native runtime: generation is an
intermediate review/verification step. Final deployment should apply the small
reviewed change to the canonical source and share its leaf implementation with
benchmarks, rather than maintain two diverging production implementations.
