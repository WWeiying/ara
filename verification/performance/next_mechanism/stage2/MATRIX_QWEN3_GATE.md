# Same-Image Qwen3 Engine Pair

Closed PASS, 2026-11-09 20:08:20 PST. Output:
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_matrix_qwen3_vcs_20261109_01`.
Its 332 source/image/data pins matched before and after all 16 commands;
service exited successfully. All three new helper active pins are released.

Sources: `stage2_qwen3_rows8_20261109_02/{attn_q,ffn_gate}`; distinct eight real
activation rows, raw Q4_K weights with 128 captured columns. Each comparison
uses the same first 32 columns, all eight rows and full K2048: 256 outputs.
This is not the parent's N64/N128 complete software-call benchmark.

| Projection | Original 2xM4/N32 | Original 2xM8/N16 | Cooperative 2xM8/N16 |
|---|---:|---:|---:|
| attn_q | 18216 | 20406 | 16194 |
| ffn_gate | 18216 | 20406 | 16194 |

Both views save 20.64% cycles versus original M8 but only 11.10% versus the
better original M4, 1.125x. M4 is unchanged with CooperativeWaves enabled.
Each candidate M8 command uses 4096 native plus 4096 real borrowed beats,
with exactly three-cycle returns. No RTL recompile or synthetic MAC array.

Per M8 command: compute 7504 -> 3248; scheduler 73 -> 2153; drain 88 -> 158;
FP request blocked 0 -> 1728. FP peak occupancy stays 16, full cycles 3456,
issued uops 6144. FP input backpressure/conflict are zero. Joint start/context
occupancy was not recorded in these images; do not claim its exact attribution.

`matrix_real_vectors.c` includes the frozen original generator and passes real
weights/activations to `emit_case_data(..., NULL)`. RTL output/flags are checked
bit-exact against ordered `qbs_ref`; flags are 0x01. There is no independent
GGML projection golden and no fabricated output file. Nine host tests passed,
including byte-identical regeneration of all four older Qwen2.5 vectors.

Files belonging to this gate: `matrix_real_vectors.c`, `run_matrix_qwen3.py`,
`test_matrix_real_vectors.py`, this brief. The sealed evidence-only test's
discovery argv issue does not invalidate its explicit-directory run; use a
successor entry point for general discovery. Workers01/02 original reports
remain untouched. These are engine results, not SoC, DDR or model speedups.

The subsequent authorized integer-result-queue experiment is a separate gate;
this report and these exact images remain historical matched baselines.
