# M9 Unit/FOF E64 Two-Case Worker

New successor only. Immutable input: ../unit_fof_e64_suffix_two_prepare01,
READY 816491edd10f338f435c3bcf473cb7cc4434d1ce65fbe7cfb419dab9bce6a2c5.
Reuses its exact two SoC ELFs and independent CSV oracle; no source/reference rerun.

Frozen M9 image.json:
48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a.
jobs2, case1800s, internal3900s, systemd4200s / control-group / Restart=no.
Both cases retain VL8, complete output130/mask16/pages/PTEs/CSR oracle, no
undefined suffix. The exact eight original results and two original guards
remain mandatory. Spike HTIF and SoC CTRL are separate backend contracts.

Reuses proven frozen runner, numeric-first monitor receipts, child result
receipts, generic full CVX/backend trace validation, strict source CSV checker,
complete metadata/summary membership, raw PASS+FAIL veto, late pin/plan checks,
and the existing restored-signal late-abort terminal publisher.
First failure or monitor/logread exception cancels peers; no retry/FSDB/build.
Numeric child0/17 remains saved before any postcheck can change acceptance.

Host-only entry: test_worker.py. Preparation: replay.py prepare, then dryrun.
prepared01/ready.json contains the exact service/worker command template.
Tesla final review schema is in AUTHORIZATION.md; prepare is not DUT acceptance.
Only the authorized run queries resource availability and direct service ownership.
Runtime IDs unit_fof_e64_scenario1/2 are distinct from archived source names.
Final PASS means exactly these source-derived Sv39 singles, not Linux/full family.

Budget estimate is ~759s each at273records/s plus20%, not a measured M9 guarantee.
1800s per case remains fixed on slow or failed execution.
