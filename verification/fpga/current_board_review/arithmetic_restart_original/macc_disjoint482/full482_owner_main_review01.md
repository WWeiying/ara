# Complete482 Backend-Owner Main Check

Main independently ran the seven `test_owner.Owners` Host tests using the
actual compiled helper PCs and complete482 model. Actual checking-process
exit0, seven tests,10.874s, `OK`; no simulator or new Spike was executed.

The tests cover required per-owner completion, a deleted necessary memory
pair with an extra pair elsewhere keeping the aggregate count unchanged,
harmless CSR replay without crediting a necessary owner, illegal memory
replay, missing completion and every unused helper interior.

## Actual Predicate Selection Correction

The initial test named all-off selected mode1. Main inspected the real mask
bytes: mode3, not mode1, is the all-zero predicate. Each mode has45 active
calls, so checking only the count45 did not expose the mislabeled stimulus.
An intermediate main assumption based on the test label was immediately
rejected by that real-data check and corrected; the model was not changed.

The owner revised the selector to `not any(actual_mask_bytes)`, rather than
another hard-coded mode. Main reran the affected scope-count and all-off
owner-deletion tests: actual exit0, two tests,4.968s, `OK`. The real all-off
necessary-owner deletion is now rejected. The earlier seven-test receipt
alone is not claimed to have exercised the correct all-off predicate.

## Required Scope

The actual model contains2410 compulsory full-capacity memory owners and182
active MACC target owners, including45 actual all-off active targets. The
minimum required architectural owners is2592;300 target calls have
vstart>=VL and may be elided. This is not a required fixed total uop count:
legitimate decomposition may add uops. Require completion of each necessary
owner, not just an aggregate threshold. Formal worker admission and full482
DUT acceptance remain separate gates.
