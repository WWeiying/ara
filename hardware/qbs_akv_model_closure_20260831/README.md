# QBS + AKV Model Closure

Status: **PASS**

This index audits functional, numerical, coverage, command, logical-traffic,
and representative RTL-cycle evidence. It does not contain synthesis, PPA,
place-and-route, or full-model RTL timing claims.

- AKV shape matrix: 112/112 PASS.
- QBS profiles: 9 RTL profiles covered.
- Real models: 3 fixed-prompt Prefill+Decode executions.
- Representative AKV RTL points: 4 zero-mismatch PASS.
- QBS cross-operator model quantizations: 394 -> 309.
- Qwen Decode projection: 102585188 -> 101618782 cycles.
- `ablation.csv` records controlled-RTL and model-projection deltas.
- `support_matrix.csv` separates accelerated, fallback, and preserved paths.

Run:

```bash
python3 hardware/scripts/akv/check-goal-closure.py
```

The manifest binds every conclusion to a relative artifact path; `artifacts.csv`
records SHA-256 hashes of all consumed raw evidence.
