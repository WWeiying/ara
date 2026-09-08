# D256 shared-replay milestone

This is an explicit snapshot, not an assertion that the whole cohort passed.
`summary.json` stores statuses, source/simulator/ELF identities, complete metrics
for passing performance runs, and diagnostic evidence from failed runs.
`performance.csv` preserves failing cycles as diagnostics only; do not include
them in valid speedup calculations. All detailed performance runs use the same
4-lane/VLEN1024/16-MiB simulation executable.

The validated Gemma KV17 change is 47,393 -> 30,255 kernel cycles, with replay
bytes reduced from 69,632 to 17,408 and external K/V payload unchanged. Strong
tiled-RVV takes 35,408 cycles. D256 remains disabled by the GGML selector.

The real KV140 capture fails the existing tolerance in both tiled-RVV and AKV.
The host schedule diagnosis reproduces 18 mismatches with tile/F16 accumulation
and zero with token-online/F16. Neither tolerance nor captured goldens changed.
See `hardware/docs/akv_d256_efficiency.md` for the root cause and limits.

The earlier `bit_exact` fixture was explicitly superseded after its input
initialization proved unnecessarily expensive. The replacement uses the same
deterministic values preloaded into the ELF; no comparison or shape was removed.
The original handoff run `d256_reuse_regress_20260907` failed at link time because
an included assembly dependency was missing. `_r2` is the separate rerun after
that build dependency was fixed. These are not masked RTL failures.

Long tests finish in the background. Their final automatically collected report
is under `hardware/akv_d256_efficiency_runs/final_summary/`, not silently written
over this committed snapshot. To collect explicitly:

```sh
python3 verification/akv/summarize_d256_efficiency.py \
  --output hardware/akv_d256_efficiency_runs/final_summary \
  --handoff hardware/qbs_akv_portability_runs/d256_reuse_regress_20260907_r2
```

`complete` means all selected tasks finished, including failures; `all_pass`
means every selected test passed. Neither is inferred from process existence.
