# Full96 Reference and VCS Adapter Ready

Status: **NF7_FULL96_PREFLIGHT_PASS_NOT_LAUNCHED**.
No NF7 VCS execution, rebuild, RTL edit, accepted fixture/oracle change or prior
sealed-input edit was performed. This supersedes the pending-reference status
in `REFERENCE_PROGRESS.md` without altering that earlier report.

## Reference Acceptance

The single terminal inspection of `ara-indexed-nf7-sv39-reference03.service`
observed inactive, MainPID0, Result=success and ExecMainStatus0. Its76 trials,
combined with the earlier20, cover original trials0..95 exactly once.

`vcs_plan01/reference_acceptance.json` records **24 groups, 96 trials and284816
successful scalar comparisons**. All96 remain source-derived real-Sv39
reference PASS, not original Linux replay or DUT PASS. Original ELF/assembly
and current C identity limitations remain unchanged.

## Prepared Plan

- Plan: `vcs_plan01/plan.json`.
- SHA256: `fcad03c47c6bcb391c090b448289f8e6a6b65285177f6ab1e4fd9c2e8ed85d14`.
- Same candidate02 image ledger:
  `384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810`.
- 24 accepted SoC ELFs, four fixed original trials per ELF; no small-subset substitute.
- All24 sealed-runner DRY_RUN results accepted, no simulator executed.
- Max4 NF7 jobs, fixed2400s simulator limit per group, separate2700s orchestration
  limit including teardown/extraction; no automatic timeout increase or retry.
- 393 direct input pins plus full frozen539/image/configuration/source-manifest
  verification through the accepted candidate02 gate.

`vcs_adapter.py` contains a preparation entry point and a separately gated
worker. The worker is **not launched or authorized by this document**. A later
parent launch must supply the actual NF2 and arithmetic service unit names,
confirm NF2 is terminal, reserve arithmetic's at-most4 slots, and explicitly
authorize the at-most4 NF7 workers. Existing simv processes outside the approved
arithmetic unit cause immediate refusal. There is no waiting loop.

Future terminal output in this prepared directory: `vcs_plan01/complete.json`.
Per-group output: `vcs_plan01/groups/gNN/complete.json`; first CSV error:
`vcs_plan01/groups/gNN/firstfailure.json`. The full96 aggregate cannot PASS if a
group failed, timed out, was cancelled or never launched. No arithmetic or other
successor is automatically launched.

## Verification of the New Adapter

| Evidence | Result |
| --- | --- |
| csv_host01/status.json | Accepted load trace,11924 comparisons,15 rejected corruptions |
| csv_host02/status.json | Accepted unmapped store trace,12078 comparisons,15 rejected corruptions |
| csv_host03/status.json | Partial-store/alloff trace,11722 comparisons,15 rejected corruptions |
| runner_host01.json | 18 negative gates; real host append/partial-line firstfailure; max4 workers; queued20 cancelled |
| actual_scalar01.json | Completed extended8 DUT CSV:88041 loads,42434 stores,6004 offset accesses decode correctly |
| host_tests01.json | Original96 host partial-field/tail validity and69 corruption negatives |

The CSV host positives are Spike-derived synthetic RVFI, not NF7 hardware
measurements. The extended8 decoder check is likewise not an NF7 DUT result.

`csv_oracle.py` verifies every scalar comparison against the accepted reference
sequence, independently checks observed checkpoint memory, and checks CSR/trap
records, permitted tval, retry PC/vstart, prefix poison, guards, counters,
restoration, magic and CTRL completion. The unchanged sealed runner additionally
requires simulator and UART completion. Live error detection uses append events;
firstfailure stops dispatch and cancels owned in-flight processes.

## Semantic Review

See `VCS_REVIEW.md` for the specification-backed review. Fractional `mf2` upper
physical-register halves remain strict under `tu`; they are not discarded as
unallocated bytes. Faulting segments may partially complete fields. Permitted
protected-field tval and intermediate validity masks remain exact; no segment
atomicity or minimum-field tval assumption is introduced. Final fields/memory,
inactive elements, full tails and guards are not relaxed.
