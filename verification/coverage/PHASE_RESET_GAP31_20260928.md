# Phase-specific reset coverage, 2026-09-28

## Scope and checks

This is a separate, coverage-instrumented build of the current verification
worktree at `verification/out/phase-reset-coverage-20260928-01/sim/simv`.
Its source manifest passed at build and at each run. These four VDBs share
one image; they are **not** merged with the older 510-PASS frozen-image set.
The reviewed waivers for that older image do not apply to this build, so the
scores below are raw DVE scores from these four tests only.

The testbench resets after a selected Ara AXI read acceptance. Read index 1
targets the descriptor fetch, while index 2 targets a QBS data fetch or AKV
payload fetch. A later index does not by itself prove an engine state: the
single-test FSM VDB was inspected for each target transition. Each run also
requires the application self-check and independent UVM audit to pass. For
each of the four runs, UVM recorded exactly one aborted AXI read and one
aborted backend VID, no issues, and an application PASS after restart.

| Engine | Read index 1 | Read index 2 | Checked result |
| --- | --- | --- | --- |
| QBS | `DESCRIPTOR_WAIT -> IDLE` | `RUN -> IDLE` | Q4_K x Q8_K output 256.0 and 31 zero tail elements |
| AKV | `DESCRIPTOR_WAIT -> IDLE` | `PAYLOAD -> IDLE` | D96, 9 rows, 864 checked elements, zero errors |

The single-engine `state_q` FSM coverage is 17/30 to 18/30 points for QBS and
20/36 to 21/36 points for AKV when read-index-2 tests are added. The DVE
module-level FSM percentages below use a different aggregation denominator;
they must not be substituted for the `state_q` point counts.

| Current-image test set | Top score | Line | Toggle | FSM | Condition | Branch | QBS module FSM | AKV module FSM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Two descriptor-read resets | 30.90% | 50.51% | 9.71% | 9.91% | 38.25% | 46.13% | 10.63% | 48.48% |
| Four resets, including RUN/PAYLOAD | 30.97% | 50.51% | 9.73% | 10.24% | 38.25% | 46.13% | 11.42% | 54.55% |

Reports: `verification/out/phase-reset-descriptor-dve-20260928-01/summary.csv`
and `verification/out/phase-reset-four-dve-20260928-01/summary.csv`. Both DVE
exports completed without diagnostics; `selected_tests.txt` lists exactly the
audited VDBs. No waived percentage is claimed for this changed RTL image.

## Reproduction

Use the compiled image above and fresh output directories. The runner's
`ARA_VCS_CODE_COVERAGE=1` option produces one VDB in the same run as the UVM
audit. Set `ARA_UVM_RESET_READ_INDEX=2` for the new scenarios; index 1 is the
default and preserves the original testbench behavior.

```bash
ARA_VCS_CODE_COVERAGE=1 ARA_UVM_RESET_READ_INDEX=2 \
  bash verification/uvm/run_real_dut_case.sh \
  verification/out/phase-reset-coverage-20260928-01/sim/simv \
  apps/bin/qbs_reset_read_cov qbs_run_reset_read \
  verification/out/NEW_QBS_OUTPUT read

ARA_VCS_CODE_COVERAGE=1 ARA_UVM_RESET_READ_INDEX=2 \
  bash verification/uvm/run_real_dut_case.sh \
  verification/out/phase-reset-coverage-20260928-01/sim/simv \
  apps/bin/akv_d96_gap29 akv_payload_reset_read \
  verification/out/NEW_AKV_OUTPUT read
```

## Still open

- Other QBS/AKV reset transitions require phase-selective triggers at request,
  validation, commit, fault-drain or replay states. They are not exercised by
  the two read-index choices and should not be waived merely because the
  current four-case subset is small.
- Dispatcher overlap/flush/store-response combinations need a separate
  reachable-state analysis and a controlled handshake stimulus; generic
  read-index sweeps do not address them.
- A single FP16 RNE Gap29 case was replayed on this current image at
  `verification/out/fp16-rne-current-20260928-01`. It still reported three
  failed self-checks and `tohost=3`; the UVM audit correctly failed. Its VDB
  is not part of either PASS-only report. The first architectural mismatch
  remains to be localized before running the other five rounding modes.
- PTW virtualization-stage points are RVH-disabled here. Its
  `PROPAGATE_ACCESS_ERROR` edge requires a PMP denial, while this SoC has
  `NrPMPEntries=0`; review these for reachability rather than manufacturing
  an invalid test.
