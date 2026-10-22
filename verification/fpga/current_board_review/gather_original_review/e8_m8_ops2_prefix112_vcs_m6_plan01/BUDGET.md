# Fixed Budget Admission

This is a static estimate from sealed terminal reports, not a new performance
measurement, resource survey, simulation, or guarantee. No existing live job
was queried. The case stays9000s, service10200s, jobs1, no FSDB/retry.

## Reference Scope

The completed software reference retired5,002,732 firmware instructions through
successful HTIF. The first112 original VI0 calls retain111 predecessors,
cap1024,114688 scalar results,224 guards,112 returned-vstart checks and all13
helper instructions. Successor READY SHA256 is
`e6962c38c215ec69ec0f0b3aaf5ebadaa9fb33341027a6c8d7f31fba0f135520`.
The reference-only5,050,000 debug-step ceiling is not a DUT retirement limit.

## Existing M6 Ratios

| Accepted case | Actual retired | Actual elapsed seconds | Scaled112 seconds | With20% |
|---|---:|---:|---:|---:|
| E8/M8 VX prefix66 | 2,672,460 | 4052.2917886851355 | 7585.719 | 9102.862 |
| E8/M8 VI31 prefix66 | 2,548,214 | 3559.067485047970 | 6987.271 | 8384.725 |

Formula: reference112 firmware retired * prior DUT elapsed / prior DUT retired.
The prior DUT retired count includes its normal CTRL/park path, while the new
reference uses HTIF and a different backend. The workload length, instructions,
active-lane distribution, later VL1023/1024 calls, host load and throughput are
not identical. These ratios are conditional proxies, not bounds proven for112.
The higher same-family ratio with20% is9103s, already above9000. A conservative
273 retired/s proxy is18325s before margin,21990s with20%. No smaller scope,
timeout increase, automatic retry, or success prediction follows from this.

Read-only provenance:

- `../e8_m8_ops1_prefix66_terminal_audit01/audit.json`, SHA256
  `7840992136756479dd019a95eab8534a05d99ecb07998e83fa6c698f2eb4a6ee`;
  status `E8M8VX66_DUT_CASE_INDEPENDENTLY_ACCEPTED_NOT_FULL2688`.
- `../e8_m8_ops3_prefix66_terminal_audit01/audit.json`, SHA256
  `459a253763c1227d07efe65594a11d5e527b66f9f5c50a34c10c216519bfa8d4`;
  status `E8_VI31_PREFIX66_DUT_CASE_INDEPENDENTLY_ACCEPTED_NOT_FULL2688`.
- M6 `campaign/image/image.json`, SHA256
  `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.

## Admission Contract

Formal independent reference acceptance must precede Host/prepare. Runner
review is separate. A later parent approval must bind the exact plan, unit,
reference READY and independent REVIEW, and explicitly accept the9000s budget
risk. The worker must be the direct service MainPID in its expected cgroup,
with RuntimeMaxSec10200, KillMode=control-group and Restart=no. The1200s
service headroom covers strict CSV checks, pin verification and teardown;
running out of that headroom cannot produce a fabricated PASS.

The existing runner enforces one actual case, full oracle, strict exit, late
disk-SHA re-read and sticky cancellation. A timeout is not automatically a
design bug; it is an incomplete bounded attempt, without retry. Runtime
capacity admission is deferred until explicitly authorized execution.
