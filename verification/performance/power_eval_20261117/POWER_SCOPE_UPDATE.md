# Relative-power acceptance update

The user's latest instruction narrows this campaign to paired representative
power. Small numerical discrepancies are acceptable; bitwise equivalence is
not a prerequisite for activity collection. This update does not change any
sealed input or original strict-check result.

- Keep production RTL, mapped netlists and hot kernels unchanged.
- Prefer the existing captured-data firmware rather than introducing software
  arithmetic workarounds solely to satisfy strict numerical comparisons.
- A separate power-eligibility audit may accept a completed workload with
  recorded numerical deviations. Record error magnitude, finite outputs,
  actual compute path, exceptions, bounds/guards and matched task dimensions.
- Do not accept an illegal instruction, stalled/aborted computation, corrupted
  memory or an unexecuted target path as representative compute activity.
- Keep original FAIL records unchanged. Power eligibility is not architectural
  correctness acceptance or closure of an inherited RTL bug.
- Collect comparable compute and memory-wait windows, excluding boot and UART.
  Report average power and its ratio; window activity alone cannot establish
  full-request energy. Retain the stated 1 GHz frequency assumption.

The four paired workloads in PLAN.md remain in scope. Full model, precision
repair, new synthesis and exhaustive verification are not added to this task.
