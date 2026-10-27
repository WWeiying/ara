# Complete-call result summary

After both workers finish, run from the verification worktree:

```sh
python3 verification/qbs/m4_prepared_reuse/collect_call_results.py \
  --projection verification/out/m4-prepared-qkv-vcs-20261027-01/result.json \
  --attention verification/out/grouped-pv-fresh-vcs-20261027-01/result.json
```

This command reads the completed checked receipts and does not launch or poll
simulators, modify source data or overwrite reports. Missing results, non-PASS
states, unmeasured QEMU results, source-drift failures, incomplete work and
invalid ABBA order are errors. It does not independently replay raw traces;
the worker checks remain the source of numerical and protocol acceptance.

For each workload, baseline cycles are trial 0 plus trial 3, and candidate
cycles are trial 1 plus trial 2. Speedup is the ratio of these paired sums,
not the average of two ratios. A regression remains negative in cycle
reduction and sets `improved=false`; it is not clipped or discarded.

The two measurements have different work and denominators:

| Measurement | Meaning | Cannot establish |
| --- | --- | --- |
| Earlier preparation-only result, 2.5502x | Three M4 quantizations versus one cold computation and two exact-input copies | Complete projection or model speedup |
| Full Q/V/K projection slice | Preparation, SDK and native compute/result work for all three outputs | GGML scheduling, intervening operations or full model tokens/s |
| Full quantized Decode Attention call | One captured H6/D128/T128 group, including its normal software work | All layers, all KV groups, longer contexts or full model tokens/s |

Do not multiply these speedups. Preparation is already inside projection,
and projection and Attention have different runtime weights. Model speedup
requires measured model-level phase weights and compatible optimized phase
timings, or an actual end-to-end measurement. Neither is invented here.

Five unit tests cover exact arithmetic, regressions, unfinished/QEMU receipts,
wrong native work, protocol rejection and partial/reordered trials. They pass
on 2026-10-27. They test the collector, not the running RTL jobs.
