# Legacy AKV resource-regression acceptance

This successor closes the legacy latency item in
`qbs_akv_runtime_closure_20261025.md`. It does not edit previously sealed inputs,
promote production RTL, or make a whole-model/PPA claim.

## Exact paired result

The original complete AKV unit suite runs unchanged on the original private
reader/legacy-plus-v2 storage and on the composed shared reader/unified store.
Both execute 892 commands: 221 legacy opcode commands and 671 v2 commands.
All recorded command identity, qualified fault metadata, outcome, relative
latencies and 31 counter/state fields match per command. Absolute clock ticks
are not the comparison metric. There are no differing command records.

| Quantity | Original | Candidate |
| --- | ---: | ---: |
| Accepted / completed commands | 892 / 892 | 892 / 892 |
| Pending commands / monitor errors | 0 / 0 | 0 / 0 |
| Successful commands | 865 | 865 |
| Validation faults | 21 | 21 |
| MMU / AXI response / PMA read faults | 4 / 1 / 1 | 4 / 1 / 1 |
| Sum of accept-to-first-valid cycles | 955244 | 955244 |
| Sum of accept-to-terminal-fire cycles | 956136 | 956136 |
| Sum of terminal wait cycles | 892 | 892 |

These sums describe this sequential unit stimulus, not additive pipeline stall
categories. Command-cycle counters include the suite's acknowledgement timing.
The passive monitor also independently samples actual acceptance, first valid
and terminal handshake edges before NBA, avoiding that ambiguity.

## Evidence exception and independent audit

The first attempt (`akv-legacy-latency-pair-20261025-01`) remains FAIL: its harness
rejected an inherited CVA6 TLB genvar warning. The successor admits only the
exact diagnostic, path and pinned source bytes already seen in an accepted
standalone compile. Other IPDW, port-width and missing-pin warnings remain errors.

The second attempt's simulator results and source/header/graph checks pass.
Its full evidence inventory, however, captured the service stdout `worker.log`
while empty. The worker then printed `PASS\n` after writing the result, changing
that file's hash. The original full-evidence check therefore fails. Neither the
old result nor that service log has been rewritten or relabeled as clean.

`verification/akv/legacy_latency/audit_stdout_extension.py` independently checks:

1. The expected original result hash and terminal status.
2. Both complete raw logs, exit receipts, parsed ledgers and exact comparison.
3. Original source/header/graph pins before and after the audit.
4. Every saved evidence hash, with exactly one mismatch: `worker.log`.
5. That file's old prefix hash and exactly five appended bytes, `PASS\n`.

The actual original prefix is empty. Any other appended bytes, changed prefix,
changed raw/compile log, changed image, missing receipt or second mismatch is
rejected. The original verifier's failure is reproduced and saved explicitly.
Thirteen host tests, including mutation tests of this exception, pass.

Parent execution produced `FUNCTIONAL_AND_LATENCY_AUDIT_PASS`, with
`clean_original_evidence=false`, not a clean original-worker evidence PASS.
Portable receipt:
`verification/akv/results/shared-storage-legacy-latency-audit-20261025.json`.
The complete audit is retained in
`verification/out/akv-legacy-latency-stdout-audit-parent-20261025-01/` and the
two 892-row ledgers remain in the original second-attempt output.

No simulation rerun was needed to resolve this reporting issue. This acceptance
is limited to the original unit stimulus and SRAM configuration. It does not
replace the separately planned integrated held-AR/error-drain test, ordinary RVV
Attention regression or final canonical-source packaging checks.
