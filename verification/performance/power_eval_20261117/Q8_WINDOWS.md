# Q8_0 Decode power windows

Both sides use the captured Qwen2.5 M1 N256 K896 workload. The RVV side uses
the historical ELF; the native side uses the descriptor-v2 successor with
the same data. Both passed their own matched RTL prechecks.

| Path | Proposed capture cycles | Selection from RTL evidence |
|---|---:|---|
| RVV | 62619 to 65675 | Four steady-state loop iterations (3056 cycles) |
| QBS | 19638 to 23190 | Second QBEXEC and the gap to the next command (3552 cycles) |

RVV RTL trace: `power_precheck_20261117_baseline_02/runs/legacy_q8_rvv/commit.csv`.
The loop branch at PC 0x80000478 retires at cycles 62618, 63382, 64146,
64910 and 65674. The matmul starts at approximately cycle 6698 and ends
near 178252, as bracketed by retired cycle CSR reads. The selected window
does not include quantization, setup or printout.

QBS RTL trace:
`power_precheck_20261117_native_q8_successor_01/runs/legacy_q8_qbs_sdk_v2_successor`.
Adjacent QBEXEC starts are at cycles 19638 and 23190. Ignore the cold
first command when selecting the representative compute window.

These are hypotheses from RTL traces, not claims about gate behavior.
Verify workload activity and window duration on the captured gate traces
before reporting power. Windows have different lengths and represent
average compute-phase power, not equivalent completed work or task energy.
