# NF8 Full192 Independent Review 01

Reviewed 2026-10-11 in ara_dsa_signoff_integration. Scope: proposed NF8 jobs8
driver, scheduler, capacity gate, CSV checker and existing reference metadata.
NF8 root: `../masked_translation/nf8_strided_review/sv39_full192/`.
No DUT/reference simulation launched or rerun. No source/RTL/sealed files edited.
This reviewer writes only this report under whole_register_original/.

## Blocking Findings

1. **P1: a case timeout can coexist with group PASS and aggregate PASS.**
   `vcs_jobs8.py:243-267` starts a timer whose callback writes firstfailure and
   calls abort.stop(), but the successful completion path never tests that
   failure/abort state. `:272-274` cancels the timer without synchronizing with
   an already executing callback. `:298-306` computes aggregate success solely
   from group statuses, ignoring abort.reason. A timeout during checker.finish()
   after the integration subprocess exits successfully can therefore leave a
   group marked PASS despite an explicit timeout failure. If this is the last
   outstanding group, every group can remain PASS and full192 is declared PASS.
   The same aggregate omission is relevant to late cancellation signals.

   Reproduced without filesystem writes or subprocesses: call the real
   group_worker for group47, mock successful runner/metadata/ELF checks, and
   invoke the real timer callback while mocked checker.finish() returns its
   successful result. Observed:

   ```text
   group_result=PASS
   abort_reason={group:47, analysis:{status:NF8_CSV_NOT_PASS,
     error:"2520s runner/teardown bound reached"}}
   firstfailure_written=True
   current_aggregate_pass_predicate=True
   ```

   Required fix in a successor: latch/synchronize timeout and terminal state,
   ensure timed-out/cancelled groups cannot commit PASS, and require no abort
   for aggregate PASS. Add deterministic late-timeout and late-cancellation
   negatives; timer.cancel() alone does not close an in-flight callback race.

2. **Readiness incomplete, not an observed DUT failure.** At inspection there
   was no jobs8 ready plan and no `dut_host_all192_01/status.json`. The software
   reference aggregate exists, but it is not the all48-group host CSV/ledger
   gate required by preflight. Do not launch before those gates, corrected
   driver review, immutable plan and explicit parent authorization are ready.

## Checked And Remaining

- Existing `test_jobs8.py`: all9 host-only tests passed. They exercise fixed
  budgets, pilot failure/evidence veto, max8 scheduling, queue cancellation,
  exact-cgroup reservations, inaccessible-process handling, nonterminal gate
  rejection and no implicit execute. They do not cover the reproduced race.
- Independently regenerated source-derived geometry matches all48 group case
  lists: exactly trial0..191, group g = trials4g..4g+3; 72 permission faults,
  72 unmapped faults and48 alloff cases. All96 SoC/Spike ELF hashes and48 group
  status hashes match the terminal reference aggregate. Totals:594288 checks,
  3120 recorded negative rejections with per-trial membership. This is metadata/
  identity verification, not a replay/revalidation of all large Spike traces.
- Static checker inspection retains comparison-ledger ordering, original
  instruction/target PCs, precise trap/retry, allowed partial fields, whole
  memory/tails/guards, firsterror, actual-initial-CSR restoration and CTRL/magic
  completion. All48 host CSV/ledger results still need terminal acceptance.
- Capacity arithmetic is consistent: NF7=2 + parent38=4 + gather=4 + whole=6
  + ownNF8=8 =24. Exact cgroup units prevent argv-label ambiguity, retain idle
  reservations and reject extra unreserved simulators. It remains a one-shot
  gate, not a global lock; the parent's coordinated roster remains necessary.
- Plan intends pilot0 alone, then47 groups at max8,2400s simulator/2520s case
  bounds. Seven2520s scheduling waves plus360s equals18000s. The service bound
  is not enforced by this script: verify a directly owning service with
  RuntimeMaxSec18000 and control-group cleanup before any future launch.
- Source-derived full192 Sv39 coverage is not original Linux/SIG execution or
  closure/localization of the historical169/128 aggregate errors.

Reviewed SHA256 values:

```text
vcs_jobs8.py 52b7fba3ebef917e359e70b5dab4b493df0a2f58f314e3a781826a8664fb38bf
scheduler8.py bef365da2f7175dbf94a4acdb54ae2683bfe89eca7eb7671320f3668b83a2f0e
capacity8.py 556038df3726b1a5958c1a52e7fc1cb5f7dc1f6f78f09be09bd414c3de92ceca
csv_oracle.py 8ff9b8ef6c6c117d706fc28ce2f27c3dfb0dff74fe9993f42205a0f1ad2fa9e1
test_jobs8.py 77d8bf716fd527f6a79e029f9d8ef3407e67f966c403d12dded2a5d50b5156bd
DUT_JOBS8_PLAN.md adca92e21e493ffa5c1ab3c7c81e1a188f37eb8c914a0a2d31ccaaf179507074
```

Whole-register startup review is separately complete in startup_review01.json:
six correct live simulators advanced during one bounded observation. No further
whole-register progress polling was performed for this NF8 review.
