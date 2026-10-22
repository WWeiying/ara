# Composed Operand Supplemental Coverage (Pending Independent Review)

No real DVE launch is authorized by this code task, these files, the offline
tests, or the18-point pilot. No final policy, CSR helper, RTL, frozen source,
old VDB or old report is edited. The official raw corpus remains authoritative.

## One Composition

The only report composition is the existing94 exact points + immutable107 CSR
vectors + independently reviewed1144 operand vectors = **1345 exact points**,
with the **same10 existing observer scopes**. There is no new editable policy.json.
The union is derived from the unchanged CSR/legacy admission and the gap56
accepted-coordinate seal. Duplicate/overlapping identities are rejected, not
silently deduplicated. No new wildcard, module or whole-instance waiver is allowed.
The10 inherited observers are the sole pre-existing instance exclusions; their
identities/shapes and lack of new descendants are still checked by the old guard.

Of3636 operand Branch leaves (36 instances x101), the new set is1144, the old
queue Branch set is16, and the remaining2476 are retained. The1269 originally
missing, independently retained coordinates remain included even if later tests
hit some of them. Current missing count and original retained count are separate.
CSR's full626 leaves, including519 retained leaves and PMP Branch3(187), remain
under the unchanged107-only CSR rules. Old78 non-Branch points and all10 observers
are checked through exact native signatures and the global empty reset.

The latest completed frozen-image corpus is selected by ancestry through the
unchanged CSR guard. Counts645/647/648 are not admission constants. Preparation,
prelaunch and prepublication check the unique latest tip. A newer completed tip,
ambiguous tips, membership drift or any target raw hit invalidates a prepared run.

## Two Approval Gates, One Full Report

1. **Capture**: open the compiled VDB plus independently admitted
   `qbs_gap45_context` PASS from the latest ledger. No full-hierarchy score export.
   Discover1144 native records by exact per-instance leaf selection; export,
   reset, import, re-export and reset again. This can publish only
   `NATIVE_1144_CAPTURE_VERIFIED_NOT_APPLICATION_APPROVAL`, never a waived report.
2. **Report**: require that full capture's certificate SHA, verify its snapshot,
   independent receipt, source/corpus/native pins, both parsed native exports,
   actual session state proof and unchanged-input evidence. A separate parent
   receipt then binds the combined report snapshot and captured1144 signatures.
   One full-corpus DVE session applies the **single1345-point union**, not separate
   CSR and operand reports. It uses the same fresh reset/import/re-export checks.

The18-point pilot supplies exact directive cross-checks for only those18 points
and format/API evidence. It never substitutes for discovery or approval of the
other1126. All1144 unknown native signatures remain a blocker until stage1 runs
under separate authorization and its complete result is independently reviewed.

Commands after independent code review, from the integration root:

```sh
python3 -B verification/coverage/reviewed_operand_20261004/test_capture_semantics.py verification/out/NEW_FOCUSED_CHECKS
python3 -B verification/coverage/run_reviewed_operand_dve_20261004.py prepare verification/out/NEW_CAPTURE --stage capture
# Review NEW_CAPTURE.tools; provide an independent receipt before any run.
python3 -B verification/coverage/run_reviewed_operand_dve_20261004.py run verification/out/NEW_CAPTURE --approval RECEIPT --approval-sha256 SHA
# Only after independent review of the full capture:
python3 -B verification/coverage/run_reviewed_operand_dve_20261004.py prepare verification/out/NEW_COMPOSED --stage report --capture CAPTURE_CERTIFICATE --capture-sha256 SHA
# Review NEW_COMPOSED.tools and issue a separate report receipt before run.
```

Output names are fresh direct children of `verification/out`. A claimed output
cannot be retried. `prepare` never starts DVE or creates the claimed output.
These commands are documentation, not execution or approval requests fulfilled.

Receipt fields (not a usable receipt):

```json
{
  "status": "APPROVED_OPERAND_CAPTURE_SESSION_ONLY or APPROVED_OPERAND_REPORT_SESSION_ONLY",
  "authority": "independent-parent-review",
  "reviewer": "independent identity",
  "snapshot_sha256": "reviewed OUTPUT.tools/snapshot.json SHA256",
  "baseline_collection_sha256": "reviewed latest collection SHA256",
  "native_capture_sha256": "null for capture; reviewed full capture-certificate SHA256 for report",
  "allow_one_dve_session": true,
  "allow_final_coverage_application": false,
  "operand_points": 1144,
  "existing_points": 94,
  "csr_points": 107,
  "observers": 10,
  "dve_max_seconds": 880
}
```

The statuses and numeric/null fields must be concrete, correctly typed values,
not the explanatory alternatives above. Receipts bind independent review:
separate-agent code-review evidence and parent review of the actual snapshot.
They imply neither human signoff nor cryptographic identity attestation. The
user's task-scope authorization does not approve any particular manifest; a
parent receipt must bind the snapshot actually reviewed. The approved snapshot root is
retained from the explicitly hashed receipt and never refreshed from a changed
manifest. Every runtime callback checks exact snapshot file/directory membership,
types and hashes before and after. Source/helper/tool binary pins, all VDB bytes
and member types are checked before/after; incomplete timeout audits are marked
incomplete and cannot publish success.

## Native And State Proof

The parser consumes every byte, rejects duplicate/dangling/opaque records,
checks complete instance/checksum headers, point checksums, root expressions,
and exact coordinate sets. Report-stage operand blocks must equal the externally
reviewed full capture; CSR blocks must equal the immutable qualified107. Legacy
signatures retain their existing guard. Export/import/export compares **complete
parsed records**, including annotations and signatures, by full identity. Record
order differences are allowed; content or signature differences are not.

Complete GUI inventories are enumerated before changes and again after import.
All other phases use only those scope-keyed metadata lists, reselect the full
instance, check Branch view and read back exact selected metadata. Target leaves
are individually queried as excluded. Each complete retained/reset set is queried
with DVE's ANY-excluded API: exact selection + ANY=0 proves every member included.
Every coordinate has five state rows, explicitly labeled `singleton` or
`exact_group_any_zero`; group-derived zeros are not mislabeled individual probes.
Final native export is empty globally. No input VDB save/write API is used.

The initial raw hierarchy report must equal the published latest raw CSV. The
report exports one supplemental hierarchy only after the native roundtrip gates.
After final reset it does **not** perform a third full hierarchy export. Instead
it binds the initial/published raw hashes, all input bytes, global empty exclusion
export and exhaustive inspected branch reset states. This does not independently
remeasure post-reset GUI scores; that evidence limit is explicit in status JSON.
Capture has no score exports at all. Supplemental reports never overwrite raw.

## Measured Budget Basis

Read-only mtime deltas, supplied by the parent and independently rechecked:

| Work | Measured seconds |
| --- | ---: |
| gap38,641: selected_tests.txt to full summary.csv | 197.608 |
| gap48,645: selected_tests.txt to full summary.csv | 184.643 |
| gap58,18-point/3-scope HOST pilot, whole session | 50.986 |
| Same pilot: initial-empty to final-empty | 19.958442 |

The **900s total /880s DVE ceiling** for this NEW capture and report is the
coordinating agent's planning decision under user-authorized preparation, NOT
permission to launch. Prepare/admission is a
separate bounded300s command. Runtime computes the tool allowance once from
remaining total time, reserving15s for postchecks and3s for cleanup; it rejects
prelaunch work beyond40s. Both native capture admission and run admission bind
the reviewed880/900 snapshot and receipt. No automatic retry or old-wrapper
timeout change is allowed.

The complete phase measurements, operation counts, uncertainty and once-only
future sequence are in [BUDGET.md](BUDGET.md). The user did not explicitly specify
this numeric budget or explicitly accept the execution risk. It is NOT a measured
completion guarantee. The larger1500s proposal
and the earlier280s capture limit are superseded. No real run is authorized now.

## Remaining Review

Independent code review is required for this new composition and both stage
receipts. CSR code-review PASS is reused as code evidence only, not as approval
of this combined snapshot. Full1144 native capture and the composed full report
have not run. Synthetic native fixtures in unit tests are temporary and are never
emitted as application-ready native files. No adjusted coverage score is claimed.
