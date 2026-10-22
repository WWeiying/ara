# Candidate03 Launch Gate

Status: **CAPACITY_BLOCKED_NO_LAUNCH**, not a DUT result. No original47 simv
process or service was started. No image build or production change occurred.
The one-shot gate was not retried; no external process was stopped or modified.

Authorized configuration: exactly the reviewed47 single ELFs, jobs2,
180 seconds/case, service outer limit5400 seconds. The latter exceeds the
24-wave worst-case simulation budget4320 seconds, leaving1080 seconds for
setup, teardown and terminal identity/acceptance checks.

Intended service: `ara-fp-moves-original47-candidate03.service`.
Fresh attempt output: `vcs_candidate03_01/`; this directory now records the
refused attempt and must not be overwritten/reused for a later launch.

## Recorded Resource Gate

[resource_gate.json](vcs_candidate03_01/resource_gate.json) retains the actual
one-shot process inventory, command lines and memory measurement:

- Live simv:25, including observed NF7 two slots and alias one slot.
- Tesla controls:two reserved slots, none observed live at this gate.
- Requested original47 slots:two.
- Total live plus unoccupied reservations plus this request:29, above cap24.
- MemAvailable:185516322816 bytes, above the32GiB floor.

The job count alone blocks launch. Reservation accounting does not double-count
already-live NF7/alias processes. No speculative service or automatic capacity
polling/retry is installed. Later authorization needs a fresh output and gate.

## Pins And Acceptance

[plan.json](vcs_candidate03_01/plan.json) fixes all47 names, original/prepared
source and ELF pins, candidate03 executable/generated libraries, all frozen
snapshot sources, integration runner, and the standalone postacceptance wrapper.
All pins passed the initial check before the resource gate.

- Candidate03 image ledger SHA256:
  `e2c32c314ca85042e49517476d36c93d0d1f8a9c8eae75d86602cef1de476cb6`.
- Reviewed47 programs manifest SHA256:
  `9f36fdf5b60ad89ac9a3aede4975d7a3d39ba55d86a5db3af5e40730f5b78fcb`.

`candidate03.py` reuses `integration/run.py`, never builds, and only produces
an accepted terminal result after COMPLETE/exact47/PASS checks, successful
runner and firmware exits, exact original one-case markers, private ELF/input
command identity, and a fresh full pin verification. Any `RVV_FP_MOVE_*FAIL`,
`BOARD_CASE_FAIL`, replay failure/trap/mismatch or fatal failure marker vetoes
success even if success strings coexist. Partial results are not acceptance.

Host checker tests: **5/5 PASS**, with nine contradictory failure-marker
variants, valid acceptance, incomplete output, wrong count and nonzero firmware
exit. See [postaccept_host.json](postaccept_host.json). These are host-only
checker tests, not additional architectural cases or VCS evidence.
