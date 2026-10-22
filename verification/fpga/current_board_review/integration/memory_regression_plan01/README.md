# Candidate02 Arithmetic Replay Plan

Prepared only. No new VCS process, software build, RTL build, or RTL edit.
Ten host tests pass; all38 generated runner results are DRY_RUN, not DUT PASS.

- Script: `../replay_memory_regression.py`, SHA256
  `4c317b218d8558c09035f2b5b728f936df1b9dcb33783803ff8d736f24b868e2`.
- Plan SHA256:
  `b990ea7a3b8901a666ea6223623cecd4860a8fd4c0d516d616b93013dbd777d1`.
- Candidate02 image ledger SHA256:
  `384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810`.
- Candidate02 snapshot SHA256:
  `b185f9fd8cc4a75ce5ab5ef240fb621511affd673bbc8b43fb7a2e8d64bad8a9`.

## Scope And Bounds

Exactly38 original final04 ELF inputs, copied byte-identically from retained
`tests/*/input.elf`, checked against original input snapshots and pinned
program manifests. Group counts: original extension1, large-offset slide6,
singles6, combined1, extended5, gather2, comparison5, flags sequence1,
reduction epoch1, comparison matrix4, extension matrix6. The10 already-passing
candidate02 smokes are excluded. Original pass markers are retained verbatim.

All748 pins are in `plan.json`: ELF originals/copies, source manifests, image
closure, configuration, full539-file source snapshot, shared and new runner
code, and budget/gate preflight records. Final04 historical statuses only
justify budgets; they are not candidate02 acceptance.

Four concurrent cases maximum. Each non-extension-matrix budget is1.5 times
its measured final04 PASS walltime, rounded up to60s with a180s minimum.
The comparison e16 matrix receives900s from its574.3s observation. All six
extension matrices receive1200s using the measured full/single progress bound
in `extension_overlap/final04_successor01/plan.json`. No retries or automatic
timeout escalation. The frozen runner's per-test bound is used, not a global
timeout overriding every case. First FAIL/ERROR/TIMEOUT, missing oracle or
worker exception sets the shared cancellation event; gather has no exemption.
Already-running private simulator sessions are terminated by the frozen runner.

## Launch Gates

Do not launch until parent review explicitly authorizes this exact plan SHA.
Preparation does not grant that authorization and creates no service.
The worker additionally requires the prior three extension jobs to have a
terminal result and Aquinas's `candidate02_extended8_01/complete.json` to report
`CANDIDATE02_EXTENDED8_PASS`. It checks the complete record, CSV analysis hash
and PASS, run metadata, summary, actual image closure and ELF identity against
the candidate02 preflight. Missing or failing evidence refuses immediately;
there is no gate polling or deferred auto-launch. Evidence is repinned at
launch and verified again after completion.

After explicit approval, the parent can invoke `work --out THIS_DIRECTORY`
with `--authorize-run --approved-plan-sha256` and the exact hash above in an
independent service. That command has deliberately not been executed here.
Only the eventual38-case candidate02 terminal oracle results can establish
the requested arithmetic acceptance. They do not replace Linux/memory-epoch
or broader signoff obligations.
