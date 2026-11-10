# Q4_K M8 Cooperative Engine Gate

2026-11-09; closed at 19:56:15 PST. Engine-only, not SoC acceptance.

## Evidence

- Output root: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`.
- `stage2_matrix_vcs_20261109_01/report.json` remains the original FAIL:
  the Python parser skipped one word instead of the complete multi-word probe
  prefix. No RTL assertion/numerical failure occurred in its three run logs.
- `stage2_matrix_vcs_20261109_02/offline-audit/report.json` independently
  rechecks both original synthetic logs and baseline context log, 171 source
  pins, and 40 image pins per arm. It does not relabel worker01 as PASS.
- `stage2_matrix_vcs_20261109_02/report.json` is the completed successor PASS.
  It reused byte-identical compiled images, without RTL changes/recompilation.
- Both arms retain the canonical shared reader and original SV checker.
  Original 36-case/fault and 12-case context suites passed, including M1..7,
  other-format fallback, Q4 M8/N5, FILL/REUSE/RELEASE and fault/reset recovery.
- Four real EW8 `simd_mul` + `qbs_lane_mul_borrow` represent existing lane
  resources. Ownership is engine busy; native quiescent is fixed true. This
  does not validate SoC admission, actual VMFPU ownership or CPU/DDR timing.
- Host tests: 16 original contract tests, 14 successor tests using actual logs.

## Same-Output Result

Real accepted Qwen2.5 Q4_K, K1536, 8 input rows x 32 output columns, 256 FP32
outputs. Original C-ref golden/flags and SV write checker remain unchanged;
only the candidate vector's Q4 M8 dot-cycle expectation is halved.

| Two-command schedule | Cooperative=0 | Cooperative=1 |
|---|---:|---:|
| 2 x M4/N32 | 13756 | 13756 |
| 2 x M8/N16 | 15362 | 12238 |

M8 saves 20.34% cycles versus original M8, but only 11.04% versus the faster
original M4 (1.124x). Each candidate M8 command executes 3072 native and 3072
borrowed beats; all borrowed beats return after exactly three cycles.

Per M8 command: compute phase 5628 -> 2436; scheduler 55 -> 1615;
drain 88 -> 158; FP request blocked 0 -> 1296. FP peak occupancy remains 16,
full cycles 2592, and issued uops 4608. FP input backpressure/conflict are zero.
These probes support FP request/result-drain pressure, not a definitive joint
start/context1-pending attribution. Do not add FP blocked counts to phase sums.

## Disposition

Closed functional gate; best-baseline reduction is below the 20% target. No
FIFO or SoC run authorized by this result. Next: same-image real Qwen3 attn_q
and ffn_gate, K2048, matching 8x32 outputs. Its C-ref front explicitly passes
`captured_golden=NULL`: bit-exact RTL/C-ref check, no extra GGML output check.

Ready for parent commit C: `qbs_profile_engine_int.sv`, `qbs_compute_engine.sv`,
`matrix_lenders.sv`, `run_matrix.py`, `test_run_matrix.py`, `check_matrix_v2.py`,
`test_check_matrix_v2.py`, `run_matrix_v2.py`, and this brief. Historical pins
remain immutable; workers01/02 have finished and no longer hold active leases.
The new Qwen3 front belongs to the next gate, not this closed acceptance.
