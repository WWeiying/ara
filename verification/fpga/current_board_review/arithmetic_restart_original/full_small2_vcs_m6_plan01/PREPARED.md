# Prepared, Not Admitted

Host03:14 test methods PASS, including14 scoped negative subcases and the two
complete4095/5985-call positives. Actual Host command exited0 in62.345s. Failed
host01 and interrupted host02 remain preserved. No DUT/reference/build was run.

Prepare exited0; dryrun exited0 with exactly two commands and no process launch.
The plan pins860 inputs, including original raw reference, fixed reference
checker/model/full results, source/helper identities, both unchanged SoC ELFs,
M6 snapshot/image/config and imported project helpers. Resource/service checks
are deliberately deferred to an explicitly reviewed launch.

| Artifact | SHA256 |
| --- | --- |
| prepared01/plan.json |7ec58e3f38f5877838c7edf898d4b85d4872437dcdc54e7542357e8f2736f9ee|
| prepared01/ready.json |e52683bb0ef533753c300f710a7476a64c3726700068c3075700c11330564daa|
| prepared01/dryrun.json |d0047cdeca7cf684a290f6f77ebd5a678304bb0e8cf1eee3108affcf0e2486a1|
| checker.py |18c9b86ab1a13b05d0f69823299d761a1f54a8d7c20c8b1ca30afd867ec8bf0f|
| replay.py |6c0e0cdd077460c6b2937c901f7fc85fc03b5756c55ca3a08261a2eedd8e9ebc|
| host03.json |1b9d00442ff9fe7cf706584a7dc435d95fccb6c4df5ffc91ebd8da62d17a886e|
| M6 image.json |a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0|
| M6 snapshot.json |3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438|

Full reference READY remains
`db878aa262c882af8cf32dfa803426382b3869c1a0f47662c4a434bd8b6439b6`;
actual offline outcome remains
`ff4102cfa0fe768a2f4bd44c25c99c4e7a8639e03af664721ea7039098a95f27`.
Own approved checker acceptance is not an independent-agent full-reference PASS.

Fixed budgets:jobs2,10800s each,12000s worker plus observers,13200s direct service.
e32's slow measured M4 proxy plus20% exceeds10800s; completion is not guaranteed.
No oracle reduction, retry, FSDB or automatic budget increase exists. Future
timeouts retain actual numeric child outcomes and are not classified as RTL
bugs without signal/progress evidence. The runtime/historical name adapter and
durable outcome hook run before postchecks, including generic trace validation.

The exact future service command is in prepared01/ready.json, with required
independent-entry and parent-review placeholders. Both gates are still pending.
Prepared files are now frozen for independent review; do not launch this plan
without those actual pinned approvals.
