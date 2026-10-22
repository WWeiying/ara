# Independent Terminal Review: Negative Stride Remaining38

## Decision
Accept the existing **M6 source-derived38-case terminal evidence** within its stated scope. No missing group, failed child/checker receipt, or pin drift was found. **Final outer worker/service exit remains unknown.** This is not unconditional service-lifecycle acceptance.

## Evidence
- Plan: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/masked_translation/negative_stride_remaining38_batch01/sv39/vcs_m6_plan02/prepared01/plan.json`
- Plan SHA256: `7be8022de6dda35da836fede4e907d31c9e329a1e7608a8c080a70a81aeb76d1`
- Terminal: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/masked_translation/negative_stride_remaining38_batch01/sv39/vcs_m6_plan02/prepared01/complete.json`
- Terminal SHA256: `9b120d7be5117e40e3151e8b2cc0e2444a55cb2e5caafb4a39f0b2b455fa83c8`
- Terminal status: `PASS_M6_NEGATIVE_STRIDE_REMAINING38_NOT_LINUX`; retries0, aborted=false, pins_unchanged=true.
- Fresh prior-review hashing checked **1229 input pins +133 terminal evidence pins =1362 unique files**, including all actual CSVs. No mismatch. Actual tool-process exit0;104.54013014119118s.
- The original executed Python body is preserved in `PIN_CHECK_COMMAND.py`; `PIN_RECEIPT.json` explicitly transcribes the observed tool execution, not a fabricated subprocess receipt or a new execution.
- For this documentation step only small metadata/ELF identities were rechecked. No CSV semantic reparse, DUT, Spike, build, live query, or ledger edit.

## Existing Full-Checker Results
**62,280,086 CSV rows /62,275,474 retired records** are counts from the existing complete strict/generic checker outputs. This review verified the actual CSV identities and matching reports; it did **not independently parse these62m rows semantically again**.

| Group | Cases | Checks | Simulator numeric exit | Offline actual wait | Simulator seconds |
|---|---:|---:|---:|---:|---:|
| group00 | 4 | 68602 | 0 | 0 | 7240.216 |
| group01 | 4 | 68604 | 0 | 0 | 7234.767 |
| group02 | 4 | 68598 | 0 | 0 | 7362.885 |
| group03 | 4 | 68604 | 0 | 0 | 7476.558 |
| group04 | 4 | 68166 | 0 | 0 | 7345.206 |
| group05 | 4 | 68602 | 0 | 0 | 7356.346 |
| group06 | 4 | 68385 | 0 | 0 | 7371.302 |
| group07 | 4 | 68602 | 0 | 0 | 7416.061 |
| group08 | 4 | 68386 | 0 | 0 | 7214.693 |
| group09 | 2 | 34092 | 0 | 0 | 4006.017 |
| Total | 38 | 650641 | all0 | all0 | |

All10 groups have strict PASS, generic VALID, no monitor timeout/failure/abort, and no offline timeout. Child command digests agree with actual command files; all private ELFs match the plan, all commands select frozenM6, and all38 source names are unique. Console logs contain exactly one batch PASS, tohost0 and finish. Actual CSV final cycles match reports. Full per-group commands, hashes, source members, child/monitor receipts and offline wait records are retained in `TERMINAL.json`.

## Boundaries and Next Action
`service_start.stdout.wait.json` proves only systemd-run submission exit0. Neither it nor a PASS console line establishes the final outer worker exit. No final service-exit or residual-process assertion is made.

This closes the evidence gap for the **38 grouped M6 source-derived scenarios**, not original continuous40 history, original parent96, Linux ABI, or M7/M8/M9 regression. The two separately accepted singles remain separate evidence.

CURRENT_SCOPE.md:140-149 and CURRENT_REPAIRS.md:70 still describe only8 cases/137206 checks. Parent can reconcile these with the full38 evidence and this explicit scope. Main ledgers are untouched.

No DUT rerun is needed. Existing optional offline entry is `sv39/vcs_m6_plan02/csv_check.py <software01/groupXX> <commit_trace.csv> <NEW_OUTPUT.json>`, per-group900s bound; output is exclusive-create. It was not executed here. An additional semantic parse requires a separate need, not merely stale documentation.
