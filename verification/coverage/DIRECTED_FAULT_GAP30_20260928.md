# Directed fault coverage extension, 2026-09-28

## Scope

These results use the frozen pre-segment-VL0-repair VCS image. They do not
represent coverage signoff for the current RTL. Only independently audited
PASS tests with compatible five-metric VDBs were appended. Existing VDBs and
reports were not overwritten; no RTL or checker was changed.

| PASS-only set | Top score | Line | Toggle | FSM | Condition | Branch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 505 baseline | 66.97% | 75.70% | 59.54% | 46.02% | 77.90% | 75.70% |
| 506 with AKV fault | 67.02% | 75.71% | 59.54% | 46.23% | 77.91% | 75.71% |
| 507 with QBS weight fault | 67.09% | 75.72% | 59.54% | 46.56% | 77.92% | 75.72% |
| 508 with AKV payload fault | 67.11% | 75.72% | 59.54% | 46.63% | 77.92% | 75.72% |
| 509 with QBS descriptor-read reset | 67.36% | 75.74% | 59.63% | 47.78% | 77.92% | 75.72% |
| 510 with AKV descriptor-read reset | 67.37% | 75.74% | 59.63% | 47.84% | 77.92% | 75.72% |

`apps/akv_descriptor_fault_cov/main.c` issues `AKVFILL` first with an
inaccessible descriptor address, then with an addressable but invalid-version
descriptor. It checks the load-access and illegal-instruction traps separately,
then checks all 32 elements of an ordinary RVV add after both failures. Its
coverage replay reported two expected exceptions, zero UVM errors and zero
protocol errors. It newly covered both `DESCRIPTOR_WAIT -> FAULT` and
`VALIDATE -> FAULT`. The AKV engine FSM increased from 63.64% to 72.73%; its
read engine FSM increased from 71.43% to 85.71%.

`apps/qbs_weight_fault_cov/main.c` supplies a valid Q4_K/Q8_K descriptor with
an inaccessible weight base. It checks the load-access trap and all 32
destination elements for an unchanged vector register. Its coverage replay
reported one expected exception, zero UVM errors and zero protocol errors.
The VDB shows `RUN -> COMPUTE_FAULT_DRAIN -> FAULT`; the QBS engine FSM
increased from 55.12% to 57.09%.

`apps/akv_payload_fault_cov/main.c` supplies a valid AKV descriptor whose
Q payload address is inaccessible. It checks the expected load-access trap
and all 32 elements of an ordinary RVV calculation after recovery. The VDB
shows `PAYLOAD -> FAULT`, distinct from the descriptor-read fault. Its replay
reported one expected exception and zero UVM/protocol errors. After this
third new test the AKV engine FSM is 75.76%.

The functional runs and independent trace audits are in
`verification/out/akv-descriptor-fault-cov-audit-20260928-02` and
`verification/out/qbs-weight-fault-cov-audit-20260928-01`, plus
`verification/out/akv-payload-fault-cov-audit-20260928-01`. The accepted
PASS-only coverage reports are in
`verification/out/vcs-original505-akv-fault-20260928-01` and
`verification/out/vcs-original506-qbs-weight-fault-20260928-01`, then the
final `verification/out/vcs-original507-akv-payload-fault-20260928-01`. The first
AKV coverage replay used a relative simulator path and was rejected by the
VDB identity check; only the absolute-path replay in
`akv-descriptor-fault-cov-vdb-20260928-03` was admitted.

`apps/qbs_reset_read_cov/main.c` starts with a valid Q4_K/Q8_K QBS command,
making its descriptor fetch the first Ara read. The testbench injects one
controlled reset during that read. Both the functional and coverage replays
completed the application self-check; independent UVM checks recorded one
aborted AXI read and one aborted backend VID, with no issues. The single-test
VDB covers `QBS_ENGINE_DESCRIPTOR_WAIT -> QBS_ENGINE_IDLE`. The accepted
509-test report is in `verification/out/vcs-original508-qbs-reset-20260928-01`.
The QBS engine FSM increased from 57.09% to 57.48%. The larger top-level FSM
increase includes reset activity in other modules and should not be attributed
entirely to QBS.

The existing `akv_d96_gap29` ELF was replayed with the same controlled reset
at its first Ara read, an AKV descriptor fetch. The application checked all
864 elements and reported zero errors in both functional and coverage runs.
Independent UVM checks again observed one aborted AXI read and one aborted
backend VID, with no issues. The single-test VDB covers
`AKV_ENGINE_DESCRIPTOR_WAIT -> AKV_ENGINE_IDLE`. The accepted 510-test report
is in `verification/out/vcs-original509-akv-reset-20260928-01`; the AKV engine
FSM increased from 75.76% to 78.79%.

## Remaining gaps

- Six prepared FP16 Gap29 tests passed Spike but failed on the frozen VCS
  image. One RNE case was also checked on the separately compiled VL0-repair
  image and still returned `tohost=3`. None is included in PASS-only coverage.
  Determine the first architectural mismatch before modifying RTL or retrying
  the matrix.
- Dispatcher FSM is 44.87%. Point inspection shows the remaining edges are
  predominantly overlap, flush and store-response combinations. Another
  generic VL/LMUL sweep is not justified; each reachable edge needs a
  specific phase/timing scenario and result check.
- PTW has one state machine at 17/26 points; its separate virtualization-stage
  FSM is 0/9 in this RVH-disabled configuration. Review those compiled points
  for reachability rather than treating all nine as missing software tests.
  The PTW `PROPAGATE_ACCESS_ERROR` path requires a PMP denial, but this SoC
  sets `NrPMPEntries=0`; do not treat a bad page-table address as a reliable
  stimulus for that transition in this configuration.
- QBS descriptor-wait reset is now covered. Its other reset/abort transitions
  remain unhit; each needs a controlled phase-specific scenario rather than
  a normal application ELF.
- AKV descriptor-wait reset is now covered. Its remaining reset/abort edges,
  including descriptor-request, payload and replay phases, likewise need
  phase-specific stimuli and independently checked cancellation. A separate
  current-image experiment subsequently covered the QBS RUN and AKV PAYLOAD
  reset edges; see `PHASE_RESET_GAP31_20260928.md`. Its raw scores must not be
  merged with the frozen-image set above.

`inspect_fsm_gaps.py` now correctly slices multiple FSMs within one instance;
that repair affects only offline coverage inspection.
