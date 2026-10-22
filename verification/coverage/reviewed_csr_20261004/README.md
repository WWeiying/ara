# Supplemental Reviewed CSR Report

Implementation for independent application review. No real DVE session has
been launched for this wrapper. Gap50 qualifies native identity only; it does
not authorize this supplemental application or change the failed gap40 strict
byte-order gate. No final coverage policy is updated.

## Scope and Admission

- Preserve the existing 94 exact points and 10 observer scopes. Add exactly
  107 constant-guard CSR Branch vectors from the original gap40 `branches.saved.el`
  sealed by gap50. Do not add CSR Blocks or PMP invariant `Branch 3 (187)`.
- `guard.py` reruns the sealed gap50 read-only qualifier and the unchanged old
  policy guard. Source, configuration, image, shape, native, independent-review,
  admission, code, and all input VDB file hashes are bound in the snapshot.
- Select the unique latest completed frozen-image aggregate by ancestry, not
  filename/mtime. Reject ambiguous tips, a stale requested baseline, hash drift,
  changed membership, or a newer completed corpus before/after execution.
- Read every admitted PASS raw branch XML. Match the actual XML vector ID and
  position to compute `base + width - 1 - position`; never substitute vector0
  or demand a two-vector `10` witness for the CSR additions. Require all 107
  actual bits zero in each PASS and the full 626-bit union equal to the sealed
  latest combined-bits cache. Legacy assumptions remain confined to the old 94.
- On `run`, rehash every prepared input byte and membership to bind the reviewed
  raw-zero evidence; do not repeat the expensive XML parse before the session.

## Offline Commands

Run from `/home/wangwy/openproject/ara_dsa_signoff_integration`:

```sh
python3 -B verification/coverage/reviewed_csr_20261004/test_wrapper.py
python3 -B verification/coverage/reviewed_csr_20261004/test_latest_corpus.py
python3 -B verification/coverage/run_reviewed_csr_dve_20261004.py check
```

Tests write only inside this new helper directory and remove their temporary
fixtures. Unit tests deny real DVE launches; the full hook runs against a local
Tcl API model with post-8.4 commands removed. Static checks also reject newer
expression syntax and expansion. This is not a real Tcl 8.4 interpreter or a
substitute for host DVE verification. `latest-check.json` records the separate
bounded, read-only corpus check; it is not an application approval.

The integration test requires gap48 `gap48-current-20261004-01` to remain the
latest completed aggregate, currently 645 admitted PASS cases. Its raw top-level
report is Line 77.08%, Condition 79.25%, Branch 77.41%, FSM 53.44%, Toggle 59.77%.
The 1144 queue parameter-guard candidates are not admitted or merged here.

## Preparation and Independent Review

`prepare OUTPUT` performs admission and writes a fresh `OUTPUT.tools` snapshot,
without creating the report directory or starting DVE. OUTPUT must be a fresh
direct child of `verification/out`. Review the complete snapshot, generated
201-point union, exact 107 CSR blocks/header, inputs, source/configuration pins,
raw-zero audit, and executable hook before authorizing any run. The original
native file is copied without rewriting it; only the new union contains the
old 94 plus the original 107.

The independent parent must provide a separate JSON receipt with these fields;
this documentation is not a receipt and the wrapper does not issue approvals:

```json
{
  "status": "APPROVED_SUPPLEMENTAL_CSR_REPORT_ONLY",
  "authority": "independent-parent-review",
  "reviewer": "<independent reviewer identity>",
  "snapshot_sha256": "<SHA256 of OUTPUT.tools/snapshot.json>",
  "baseline_collection_sha256": "<admitted latest collection SHA256>",
  "allow_one_dve_session": true,
  "allow_final_coverage_application": false,
  "existing_points": 94,
  "csr_points": 107,
  "observers": 10,
  "blocks_added": 0
}
```

Only after that review, `run OUTPUT --approval RECEIPT --approval-sha256 SHA256`
can start one session. These fields bind a human review decision; they are not
a cryptographic attestation of reviewer identity. Missing, stale, changed, or
identity-only receipts fail before launch. The output directory is a one-shot
claim; any failed attempt requires new preparation and independent review.

The approved manifest SHA is retained from that receipt, never refreshed from
`snapshot.json`. The wrapper checks that root and exact bundle membership before
import/launch, after the session, and immediately before success publication.
Every runtime adapter invocation requires `--snapshot-sha256`; Tcl callbacks
receive the original root through `CSR_SNAPSHOT_SHA256` and check the entire
bundle both before and after their work. Files, directories, and member types
must match; extra/missing members and symlinks are rejected. Rehashing a modified
hook into a modified manifest does not authorize it. Final status records only
the originally reviewed root. See `review-response.md` for the independent P1
finding and regression coverage; independent re-review is still required.

## Future Session Gates

The copied, unchanged exporter opens only the admitted compile/PASS inputs and
writes the raw summary first. The new Tcl 8.4 hook then:

1. Saves empty initial exclusions and checks raw summary against the baseline.
2. Enumerates all 626 CSR coordinates and verifies exact selected metadata.
3. Loads the one union file, applies only the existing 10 observers, recalculates,
   and requires empty imported-exclusion review.
4. Rechecks all 626 identities, 519 retained neighbors as included, and each
   of the 107 selected leaves separately as excluded.
5. Saves the native union and requires exactly 201 point records plus 10
   observers. CSR annotation/directive blocks and header are byte-exact to the
   qualified original, keyed by identity, independent of record ordering.
   Reject duplicates, missing/extra points, dangling headers/annotations, and
   unparsed syntax; never relax a point identity or mark the old strict gate PASS.
6. Exports a separate supplemental summary, resets exclusions, checks all 626
   included and empty native state, and exports the raw summary again.

Finalization checks the fresh markers, selected PASS population, unchanged VDB
membership/hashes, unchanged receipt/pins, and still-latest corpus. Raw reports
remain separately under `raw/`; the supplemental report is `summary_waived.csv`.
Success is named `SUPPLEMENTAL_CSR_REPORT_VERIFIED_NOT_FINAL_SIGNOFF`, never the
old policy's `APPLIED`. A failure publishes `REJECTED_NO_SUCCESS_CLAIM`.

The wrapper has a 170-second wall-work alarm with 3 seconds reserved for process
cleanup. DVE has at most 150 seconds and less if admission consumed time. A
dedicated process group is killed unconditionally, including Xvfb/callbacks;
there are no retries, simulations, URG/Verilator calls, or VDB write APIs.
Full-corpus DVE may exceed this bound; timeout is a failure, not permission to
relax gates or extend the budget. Real union serialization and live state
checks remain untested until independently authorized execution.
