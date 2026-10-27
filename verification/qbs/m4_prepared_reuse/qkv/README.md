# Complete Q/V/K projection comparison

This experiment measures whether the accepted preparation optimization still
helps when the native matrix work, SDK dispatch and result stores are included.
Both sides use the same QBS hardware and weights. It is not RVV versus QBS,
and it is not a whole-model timing measurement.

## Workload

The input is the first four real Prefill rows captured from Qwen2.5-1.5B
Q4_K_M, layer 0. Q, V and K inputs are independently checked byte-identical.
The experiment retains every output channel and all K elements:

| Projection | Activation | Weight | Weight profile | Output |
| --- | --- | --- | --- | --- |
| Q | 4 x 1536 | 1536 x 1536 | Q4_K | 4 x 1536 |
| V | 4 x 1536 | 256 x 1536 | Q6_K | 4 x 256 |
| K | 4 x 1536 | 256 x 1536 | Q4_K | 4 x 256 |

Each trial computes 8192 FP32 outputs using 64 native commands. Four ABBA
trials use recomputation, cache, cache, recomputation. Each cache trial starts
cold, computes once, copies prepared bytes on two exact-input hits and releases
the entry after the final consumer. Separate destination buffers are reset
before every trial; leaving previous workspace contents untouched cannot pass.

## Checks and timing

- Capture metadata, binary hashes, source inputs, libraries, ELF and simulator
  image are pinned. Drift is an error, not an opportunity to relabel old data.
- Every prepared byte matches the previously accepted producer image.
- All output elements must be finite and match the pinned reference within
  fixed tolerances. Q uses an independently decoded reference; V/K use captured
  GGML outputs. Optimized and baseline outputs must also be bitwise identical.
- Input/weight integrity, output/packed-buffer guards and FCSR/VCSR are checked.
- The independent protocol checker must pass. The vector trace must contain
  exactly 256 M4 native commands and 131072 nonduplicated result bytes.
- Timed regions include admission, quantization, allocation/snapshot/copy,
  release, SDK calls, native work and output stores. They exclude integrity
  checking, initial weight repacking, GGML graph scans/thread scheduling and
  intervening model operators. Cache construction is outside the region.
- QEMU is a functional gate only. Its distinct success marker cannot be
  accepted as hardware timing; the functional report omits cycle fields.

## Reproduction

Run from the verification worktree, using a fresh directory for every command:

```sh
python3 verification/qbs/m4_prepared_reuse/build_qkv_projection.py \
  --output verification/out/NEW_BUILD
python3 verification/qbs/m4_prepared_reuse/qkv/reference.py \
  --build verification/out/NEW_BUILD --output verification/out/NEW_REFERENCE
python3 verification/qbs/m4_prepared_reuse/qkv/run.py \
  --build verification/out/NEW_BUILD --output verification/out/NEW_PREFLIGHT
```

After reviewing the gates, run the same worker with `--execute-reviewed` and
another fresh output directory. Long runs must have an independent owner
service; merely backgrounding a launcher does not guarantee worker survival.
The execution bound is 10800 seconds. Do not modify pinned inputs while it runs.

Accepted functional evidence:
`verification/out/m4-prepared-qkv-reference-20261027-01/result.json`.
It reports four successful trials, exact paired output/state and two cache hits
per optimized trial. No timing claim is made from that report.

The hardware run launched as `m4-prepared-qkv-vcs-20261027-01.service`, using
`verification/out/m4-prepared-qkv-build-20261027-02`; its independent output is
`verification/out/m4-prepared-qkv-vcs-20261027-01`. At launch acceptance the
actual VCS process and progressing cycle trace were observed. Consult its
`status.json` and final `result.json`; launch acceptance is not a result PASS.

## Interpretation

The earlier 2.55x result applies only to three preparations. Use the complete
trial totals here to report projection speedup, not that preparation ratio.
Even a passing complete slice does not include graph-policy overhead or prove
model tokens/s improvement. Normal-library model output/activity checks are a
separate gate, documented in `hardware/docs/q8k_m4_prepared_reuse_design.md`.
