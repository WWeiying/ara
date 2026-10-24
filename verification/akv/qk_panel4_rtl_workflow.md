# QK PANEL4 actual-RTL acceptance workflow

This is an opt-in software scheduling candidate, not a newly enabled hardware
feature or an established performance gain. `AKV_QK_PANEL4=1` selects the shared
native helper only for supported F16/D128/six-query-head plans after real
capability discovery. Missing environment support and all other plans retain
the existing path. REFILL overlap remains OFF.

## Why VCS is the numerical gate

The available QBS-capable QEMU raises illegal instruction on native AKVINFO;
its preflight cannot certify AKV calculations. No substitute capability reader
or QEMU emulation is used to manufacture acceptance. The existing accepted
four-lane/VLEN1024/16-MiB VCS image executes both real helpers.

`qk_panel4_native/rtl_build.py` prepares eight pairs from the genuine KV128
Qwen2.5 capture: both KV heads, VL 1/64/7/63, Query strides 320/256 bytes, and
two token tiles. A separately compiled host scalar `fmaf` oracle accumulates
dimensions 0..127 after exact F16-to-F32 conversion. All source values here
are finite; this is not exceptional-NaN coverage. The test compares 3240
active FP32 outputs and 2904 inactive tail words across sixteen runs, checks
FCSR/VCSR, guards and unchanged input bytes. The worker independently checks
native command work, the actual final hardware summary and UVM boundary/AXI
evidence. Its PASS covers the score helper, not whole Attention or performance.

## Complete-operator gate

`build_qk_panel4_abba.py` rebuilds the real shared Attention runtime and both
helpers into one fixed-address ELF using the same real KV128 capture.
`run_qk_panel4_abba.py` requires the focused gate and accepted image receipts
before launching. Its four calls select OFF/ON/ON/OFF. Timing includes native
planning, Query conversion, capability selection, QK, softmax, PV and output
completion. The output checks include captured-reference tolerance, exact
cross-trial bytes, FCSR/VCSR and output guards.

Per-call expected work is 774 native commands for singles versus 390 for
PANEL4. Logical K columns, external Q/K/V reads, replay bytes and mathematical
operations remain equal. The checker proves PANEL4 use through actual command
counters, not environment labels. Trial counter totals are software-derived
from raw command records and checked against the single hardware-emitted final
summary. It does not invent per-trial hardware summaries.

## Background ownership and result locations

The focused run is owned by systemd service
`akv-qk-panel4-rtl-gate-run-20261023-01.service`, with evidence in
`verification/out/akv-qk-panel4-rtl-gate-run-20261023-01/`.

The queued complete-operator service is
`akv-qk-panel4-attention-after-gate-20261023-01.service`.
`run_qk_panel4_after_gate.py` waits on the verified focused worker's Linux
pidfd rather than polling logs. It requires terminal PASS and an unchanged
Attention worker hash before replacing itself with that worker via `exec`.
The service therefore continues owning the actual simulator/checker process
group. Gate failure, process identity mismatch or input drift prevents launch.
Its readable launch log is
`verification/out/akv-qk-panel4-pipeline-20261023-01/worker.log`; complete
Attention results go to
`verification/out/akv-qk-panel4-attention-abba-20261023-01/`.

Each simulator is bounded to three hours. No historical outputs are overwritten.
Only terminal checked PASS receipts establish acceptance; a live service or
an ELF build is not evidence of numerical success. A performance benefit must
be established from complete-operator cycles before considering promotion to
the external GGML backend. Ordinary RVV and unsupported-shape fallbacks remain
unchanged. No synthesis or physical assessment is part of this workflow.
