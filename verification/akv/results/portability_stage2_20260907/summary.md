# AKV Portability Stage 2

Measured RTL cycles only. QEMU is functional evidence, not a speed estimate.

| Cohort | Case | Mode | Status | Cycles | RVV speedup | Original AKV speedup |
| --- | --- | --- | --- | ---: | ---: | ---: |
| qbs_akv_portability_stage2_20260907_r2 | qwen_kv128 | akv_v2 | PASS | 105503 | 7.313x | 1.000x |
| qbs_akv_portability_stage2_20260907_r2 | qwen_kv128 | akv_v2_portable | PASS_REVALIDATED | 215737 | 3.576x | 0.489x |
| qbs_akv_portability_stage2_20260907_r2 | qwen_kv128 | rvv | PASS_REVALIDATED | 771502 | 1.000x | 0.137x |
| qbs_akv_portability_stage2_20260907_r2 | qwen_kv16 | akv_v2 | PASS | 35473 | 3.643x | 1.000x |
| qbs_akv_portability_stage2_20260907_r2 | qwen_kv16 | akv_v2_portable | PASS | 52179 | 2.476x | 0.680x |
| qbs_akv_portability_stage2_20260907_r2 | qwen_kv16 | rvv | PASS | 129219 | 1.000x | 0.275x |
| qbs_akv_portability_stage2_20260907_r3 | qwen_kv128 | akv_v2_portable | PASS | 108420 | 7.116x | 0.973x |
| qbs_akv_portability_stage2_20260907_r3 | qwen_kv16 | akv_v2_portable | PASS | 36348 | 3.555x | 0.976x |
| qbs_akv_portability_stage2_20260907_r3 | refact | akv_v2_portable | PASS | 143217 | 2.035x | - |
| qbs_akv_portability_stage2_20260907_r3 | refact | rvv | PASS | 291471 | 1.000x | - |

## Counter Boundaries

- `fp_issue_activity = fp_exec_lane_fires / (monitor cycles * lanes)` counts accepted FP lane operations, not peak FLOP utilization.
- `axi_ar_bytes` includes shared VLSU normal/AKV read traffic. Do not add AKV payload bytes again.
- AKV Q/KV external bytes count accepted payload strobes, excluding descriptor bytes. Replay bytes are internal traffic.
- Phase counters are inclusive diagnostics. AKV command totals are repeated on phase rows; sum them only once per run.
- Kernel cycles and monitor cycles use different marker overheads. Ratios use the matching denominator.

## Model Runs

| Cohort | Model | Status |
| --- | --- | --- |
| qbs_akv_portability_stage2_20260907_r2 | qwen25_1p5b_q4km | PASS_REVALIDATED |
| qbs_akv_portability_stage2_20260907_r2 | qwen3_1p7b_q4km | PASS |
| qbs_akv_portability_stage2_20260907_r3 | gemma3_1b_q4km | PASS_REVALIDATED |
| qbs_akv_portability_stage2_20260907_r3 | qwen25_1p5b_q4km | PASS_REVALIDATED |
| qbs_akv_portability_stage2_20260907_r3 | qwen3_1p7b_q4km | PASS_REVALIDATED |
| qbs_akv_portability_stage2_20260907_r3 | refact_1p6b_q4km | FAIL |
| qbs_akv_portability_stage2_20260907_r4 | refact_1p6b_q4km | PASS_REVALIDATED |
