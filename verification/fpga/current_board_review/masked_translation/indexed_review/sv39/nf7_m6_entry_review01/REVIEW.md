# NF7 M6 Entry Review

**Decision: HOLD. One P1 prerequisite-gate blocker needs a successor fix before launch. No DUT approval.**

## Finding

- **P1: NF2 independent acceptance is an attestation string, not a checked terminal contract.**
  `vcs_m6_current96_plan01/replay.py:145` through line154 checks four file hashes,
  the caller's `TERMINAL_INDEPENDENTLY_ACCEPTED` string, the terminal PASS label,
  `aborted=false`, `pins_unchanged=true`, a caller-supplied plan hash and image label.
  It never reads the independent review content, results/membership/retries,
  durable numeric child outcomes, runner COMPLETE, or full evidence pins.
  The README explicitly delegates review meaning to parent attestation; this is
  weaker than the requested real-complete/no-marker-only NF2 prerequisite.
- A focused real-filesystem counterexample executes only the exact authorization
  function extracted from the sealed worker AST. Hash-valid synthetic files contain
  `accepted=false`, `NOT_ACCEPTED_NO_RETRY`, `retries=1`, one wrong member with
  `status=FAIL/returncode=17`, and no durable child/run/oracle evidence. The gate
  nevertheless returns all four approval pins. No real NF2 output is involved.
  Reproduction is retained under `synthetic_prerequisite/` and `evidence.json`.
- Before launch, use a new successor to require the actual fixed NF2 plan/membership,
  all10 PASS, strict integer child rc0, retries0/noabort, runner COMPLETE and unchanged
  full evidence pins. Bind and check the actual independent `terminal01/result.json`,
  `verified_pins.json` and successful `wait01/audit_exit.json`/completion, including
  the matching actual complete SHA and M6 image. Do not infer outer service rc0.
  Reject missing, false, stale or partial evidence. Do not edit the sealed worker.

## Verified Scope

- All840 original plan pins matched before/after;870 review pins including the24
  existing dryrun commands. M6 image SHA and configuration digest match;539 frozen
  source files and66 image files are explicitly covered. No current workspace claim.
- All24 previously accepted SoC ELFs are byte-identical. Exact groups0..23 retain
  four trials each and full order0..95;284816 comparisons,168 checkpoints and168
  traps (72 architectural faults plus96 S-ecalls). No regrouping or fixture rebuild.
- Original `csv_oracle.py` and `reference.py` match old accepted pins. The isolated
  observer loads the original symbols/cases/status/ledger. Fractional-register upper
  tails, full-group guards, memory/PTE oracle, original phase1 partial-field allowances,
  full final results, retry/prefix poison and captured-initial CSR restoration contract
  are unchanged. Exact target PC/opcode checks are retained; this is not a newly added
  proof of every retired instruction against disassembly.
- `replay.py:99` persists the actual monitor result with exclusive creation and fsync
  before generic postchecks; missing command identity still preserves numeric outcome.
  `checker.py:103` requires numeric0, no timeout/failure, command binding and no oracle
  substitution. A monitor exception cannot fabricate a numeric outcome.
- Group timer cancel/join, sticky abort, final deadline quiescence and common atomic
  terminal publication prevent an aggregate PASS after a latched deadline/cancel.
  Direct MainPID/cgroup,2400s child/2700s group/16200s worker/16800s service and
  four-worker bounds are unchanged. Capacity admission remains future-only.
- Existing Host28 status/log and all24 dryrun commands were independently checked,
  not rerun. Host28 does not exercise an inconsistent NF2 authorization payload;
  only the concrete newly identified gap received a small synthetic check.

## Evidence And Limits

Plan SHA: `b29f616c1075ccf06a9294bc970382a5c7d6f897b17339b284a2bb22d829d64a`.
Image SHA: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
Worker SHA: `62e8720e80bf438f6a07f56ff2862146169d889dc76e82f5cac8b5c2299679cb`.
Evidence SHA: `3d5d2f6233f990cc567f2ffb4320d59f259b2948fa97ce293f0ef632aeb4d7e5`.
Verified-pins SHA: `8a747763f2ded3c898960ea5a357d1605006731ee5e04767ce80d358e907ecde`.

Actual inspection command: `python3 -B .../nf7_m6_entry_review01/inspect.py`.
Actual command exit0,5.002587s; this means the review/counterexample completed,
not that entry is accepted. Tool session91092, completion chunk1b28cb.
No live NF2 CSV/output/process query, CSV parse, Host rerun, dryrun rerun, reference,
Spike/build/DUT launch or sealed-file edits. NF2 event auditor remains untouched.
No M6 NF7 PASS or original Linux exact-failure closure is claimed.
