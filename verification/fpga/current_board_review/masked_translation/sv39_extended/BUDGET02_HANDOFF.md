# Extended8 Budget-Only Successor

Authorized attempt: `candidate02_extended8_02`.
Service: `ara-sv39-extended8-memory02-02.service`.
This document specifies the handoff, not a launch or PASS assertion.

One-time launch confirmation: service started 2026-10-10 22:36:53 PDT;
at age 44 seconds it was active with worker PID 3937625, sealed runner PID
3937743 and actual candidate02 simv PID 3937750. Runner argv showed jobs=1,
timeout=1800 and the new attempt's input.elf/commit_trace.csv paths.
Systemd reported RuntimeMaxUSec=35min, TimeoutStopUSec=5s and
KillMode=control-group. Last complete CSV row inspected: cycle 14493,
retirement order 9565, PC 0x80000042 (a following row was still being
written and was not treated as complete evidence). This establishes live
simulation progress, not oracle acceptance. No subsequent polling was done.

## Identity and Scope

- Original `reference01/soc.elf`: `a0219fef355612a36370851a6a4d3011bb30991afbc19459068c3728526ea982`.
- Original candidate02 image ledger: `384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810`.
- Same sealed runner, eight scenarios, software oracle and CSV checker.
- Only orchestration budgets differ: inner 1200 -> 1800 seconds, outer 1200 -> 2100 seconds; jobs remains 1. Output is relocated to a fresh directory.
- The inherited preflight performs its original 1200-second DRY_RUN only. `budget_preflight.json` and `budget_dryrun/` establish the actual 1800-second command; neither dry run executes VCS.
- All old `_01` files, including CANCELLED raw evidence and terminal analysis, are pinned and checked before/after. Reference inputs, parent acceptance artifacts, frozen sources, image files, configuration and compiled-source manifest are also checked.
- Unchanged fixture stops entry into later cases after its first error. The sealed runner retains its existing failure handling. No retries or follow-on simulations are scheduled.
- Acceptance still requires all 6227 exact comparisons, all checkpoints/traps/restarts, CSR restoration, completion magic, CTRL success and UART completion. Partial progress is not PASS.

## Terminal Handoff to Tesla / Parent

Terminal file (only exists after worker completion):

`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/masked_translation/sv39_extended/candidate02_extended8_02/complete.json`

Review together with `csv_analysis.json`, `run/summary.json`, `worker.json` and `budget_preflight.json` in the same directory. A missing terminal file or a service timeout is not PASS. The worker requires post-run identity checks to pass before emitting PASS.

The prepared arithmetic plan may be regenerated as a successor only after review of this terminal evidence. No automatic launch is authorized or implemented. This shared file is the handoff; no direct agent messaging transport was available.

## Host Checks

`test_successor_budget02.py` rejects 25 invalid budget/command/identity/authorization/ownership inputs without starting a simulator. Results: `budget02_host_tests.json`. Existing oracle and parent-gate negative tests remain unchanged in `adapter_tests01/tests.json`.

## Interruption Preserved

The previous `_01` remains CANCELLED by the 1200-second outer service limit, not a simulator-confirmed timeout. Its eight functional case boundaries and 5072 matching checks do not substitute for full-suite completion. The measured completion estimate was approximately 1253 seconds; this authorized bounded successor changes no tested semantics.
