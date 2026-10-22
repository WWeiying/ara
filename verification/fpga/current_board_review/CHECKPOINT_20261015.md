# Verification Checkpoint, 2026-10-15

This checkpoint belongs to `ara_dsa_signoff_integration`. It does not merge
the verification candidate into `ara_dsa` or change the historical coverage
population. Current source identity and evidence boundaries are recorded in
`M9_CURRENT_RTL_SNAPSHOT_CHECK.md`, `CURRENT_SCOPE.md`,
`CURRENT_REPAIRS.md` and `FINAL_PENDING_REQUIREMENTS.md`.

## Changes Included

- Eleven Ara RTL files contain the measured restart, operand-stream, mask,
  floating-point exception, layout-conversion and memory-fault fixes described
  in `CURRENT_REPAIRS.md`.
- The verification runner classifies a captured simulator timeout before a
  later shared cancellation signal. Original failure records remain intact.
- Directed tests, source adapters, strict checkers, campaign tools and review
  documents preserve original program identities and full result checks.
- Long-running simulations use independent directories, numeric exit receipts,
  automatic terminal collection and bounded execution without automatic retry.

## Latest Complete M9 Source-Port Results

| Original program | Calls | Simulator exit | Simulator seconds | Terminal evidence |
| --- | ---: | ---: | ---: | --- |
| `rvv_fp_compare_unboxed_unmasked_e32_mf2` | 17920 | 0 | 8419.734125 | `fp_compare_unboxed_e32_mf2_full17920_entry_review_hilbert01/TERMINAL_REVIEW.md` |
| `rvv_fp_compare_unboxed_e16_mf4` | 17920 | 0 | 7843.901512 | `fp_compare_unboxed_masked_full17920_vcs_m9_plan01/TERMINAL_REVIEW.md` |
| `rvv_fp_redspecial_e16_mf4` | 6720 | 0 | 3076.519100 | `ordered_reduction/full6720_e16_mf4_vcs_m9_plan01/TERMINAL_REVIEW.md` |

Each result includes the complete source oracle and actual backend lifecycle
checks, successful service and collector exits, and independent terminal
review. These three programs cover 42560 calls. They do not close the original
Linux process histories, all other parent programs, or the arithmetic m8 gaps.

## Evidence Storage

Source, tests, documentation and bounded result summaries are versioned.
Large execution traces, waveforms, simulator builds, executables, generated
tables and detailed per-instruction ledgers remain in their local evidence
directories and external archives. Paths and recorded hashes in the reports
identify those artifacts; a Git checkout alone is not the entire evidence
archive. Omission from this commit does not delete or rewrite an artifact.

The existing historical coverage population contains 798 admitted tests on
its frozen design. Current repaired RTL results must not be mixed into that
population without a compatible new coverage collection.
