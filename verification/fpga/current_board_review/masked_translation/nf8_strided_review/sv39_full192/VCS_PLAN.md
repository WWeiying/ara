# Full192 DUT Feasibility Plan: Not Authorized Or Launched

48 fixed groups, four consecutive original trial IDs per ELF. Future runner
must bind every accepted ELF, source/runtime pin, full independent reference
ledger, phase/check counts, precise traps/retry, allowed field partial states,
whole-memory/guard/CSR checks and completion magic. No tiny-subset replacement.

## Measured Calibration And Limits

Only trial19/17 terminal results have been independently audited in this turn:
470.1075s/374954 cycles and442.9078s/374876 cycles, each3122 comparisons on
candidate04. Their complete CSVs and image/ELF pins match; both had cause13,
PC0x80001566, tval0x40001000, VL8/vtype23/vstart3 and correct same-PC retry.
This is **2/4**, not aggregate acceptance. No progress query for running67/31
or NF7 was used. Fill in store/alloff calibration only after their terminal
notification and independent review; do not present this as four-point timing.

Conservative unoptimized four-case projection: approximately1500000 cycles,
1772..1881s/group. Group0's shared-initialization reference uses1001948 Spike
commits versus roughly4*287851 for isolated trial19, but different geometry and
Spike/DUT timing mean this is not a measured DUT speedup. Do not lower budgets
based solely on shared initialization or Spike instruction counts.

Proposed fixed DUT limits for later approval:2400s/group,2700s orchestration
including teardown/checker, no timeout escalation or automatic retry. At four
workers,48 groups form12 waves: expected5.9..6.3h at the two-case calibration;
hard service33600s (9h20m), allowing12*2700s plus admission/finalization.
At two workers use24 waves and a separately approved outer66000s, never the
four-worker outer limit. Store/alloff measurements may change this proposal
before any launch, not by blind mid-run escalation.

## Admission And Failure Handling

- No192 DUT launch before all192 host/Spike/negative acceptance, completed
  four-representative aggregate parent review, and explicit image/budget choice.
- Exact selected frozen image/config/compiled-source manifest and ELF interface
  checks. Existing integration runner only; no RTL/new image build.
- One fresh resource admission: total live plus all reservations <=24 simv,
  MemAvailable>=32GiB. Include NF7, controls, alias/other-session work and reserved
  slots; never stop or modify external jobs. Refuse saturation without polling.
- Proposed own maximum4 workers, reduced only in a separately pinned plan with
  matching wave/outer budget. Source/trials/oracle unchanged by scheduling.
- Event-driven scalar CSV oracle and exact independent comparison ledger;
  fail on first mismatch/default trap/incorrect count or incomplete completion.
  Stop own active jobs and cancel own queue on first failure; preserve console,
  CSV, firsterror/checkpoints and pins. No rerun, timeout increase or RTL edit.
- systemd stdout/stderr append local service log, cgroup teardown, confirm actual
  simv advancement once. No long-running progress polling. Terminal-only review
  must distinguish DUT failure, fixture/checker failure, timeout and cancellation.

Original SIG/Linux constraints remain in README. Full source-derived192 is
necessary broader coverage, but does not itself locate the aggregate169/128
error difference or prove the original Linux signal/context path fixed.
