# D256 token-order native results

- RTL/software baseline: `4410dce9368751aa474b2223bcde90144cf2bad9`.
- Source run: `hardware/akv_d256_efficiency_runs/online_order_20260908/`.
- UTC window: 2026-09-08 03:08:59 to 04:31:41; all seven tasks passed.
- `status.json` preserves per-task provenance, status and source/binary hashes.
- `successful_metrics.csv` contains six performance points; PV smoke is a
  correctness test, not a throughput benchmark.
- Gemma KV140 speedup is `419549 / 164622 = 2.54856` versus the passing plain
  RVV implementation on the same captured input and simulator. It is not a
  model-level speedup or a comparison to a corrected tiled-RVV kernel.
- Earlier failing tiled-RVV data is intentionally not used as the denominator.
