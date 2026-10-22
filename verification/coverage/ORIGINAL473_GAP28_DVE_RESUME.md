# Original473 Gap28 Collection-Only Resume

The campaign completed 521 outcomes: 503 PASS and 18 TIMEOUT. Collection
stopped before DVE invocation with a KeyError naming `outcomes/seed1417.json`.

Root cause: `extend_vcs_dve_batch.prepare` pins each predecessor outcome path
and writes a copy into the extension output, setting `reused=True`. It does
not pin the destination path. `extend_memory_coverage.summarize` indexes
`plan['files'][destination]` for inherited cases. The missing dictionary key,
not a mismatched hash or corrupt source archive, caused the stop.

The separate `resume_original473_gap28_dve.py` entry point:

- Requires the completed 521-case STOPPED/DVE state and exclusive batch lock.
- Validates the original frozen plan, image, case sources, and historical
  source archive without substituting the changed live dispatcher.
- Checks each predecessor outcome against its existing frozen hash; compares
  the copied record with exactly `dict(predecessor, reused=True)`.
- Adds 485 copied-outcome pins only in a separate collection plan. Original
  plan and plan hashes remain unchanged.
- Pins all 521 outcome files, calls the existing PASS-only summarizer, checks
  all selected VDB inventories and provenance before/after DVE, and verifies
  the exact selected-test list and waiver application.
- Preserves the prior STOPPED checkpoint, then updates completion metadata
  only after successful collection. TIMEOUT outcomes remain excluded.

Invocation from the sole signoff worktree:

```sh
python3 verification/coverage/resume_original473_gap28_dve.py
```

It is deliberately one-shot: existing `dve-resume-01` or an unexpected state
is rejected. Evidence is under
`verification/out/vcs-original473-gap28-20260928-01/dve-resume-01/`.
Reports go to that campaign's `dve/`; the runner log is `logs/dve.log`.
The helper has no prepare, schedule, worker, simulator, or build invocation.
There is no RTL modification, resimulation, repaired-image reuse, or gap29
launch. A software-process failure is recorded in the separate status JSON
with traceback; no outcome or frozen-plan hash is rewritten to conceal it.
