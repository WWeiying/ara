# M6 e8/m8 vi31 Natural Prefix66 Runner

Prepare and Host only. No DUT, RTL build, Spike rerun or live-simulation query.
The new worker derives from the sealed e16 vi31 runner, retaining first-failure,
sticky-abort, COMPLETE, parent-authorization and terminal disk-plan contracts.
No old helper, reference, source or sealed output is modified.

## Accepted Source and Exact Scope

| Artifact | SHA256 |
| --- | --- |
| ../e8_m8_ops3_prefix66_prepare01/READY.json | b15c7b86fa273aacbc464dca171a3cee3bc4140e701ed639ef70d7cc9aee5388 |
| ../e8_m8_ops3_prefix66_audit01/REVIEW.md | 0fbf49c49a1570f57c2937b99854b253b265be5a606256dc47c53177ee9d43e4 |
| Independent audit.json | 42aee537c6eacce6f968c21e77d7e3ed77910b1cb69f51c51d7af5e5920817b9 |
| Exact original-source SoC ELF | 88b154a9a1c68f2a25706eb7b8587237335b34d3bc69590f970fec0074fca841 |

The source READY retains its historical pending-review label; preparation
requires the separately pinned ACCEPTED audit/review, not a rewritten READY.

Original66 calls/65 predecessors/cap1024,67584 results+132 guards and66
returned-vstart checks remain. All13 helper instructions, RNG/setup, scalar0,
unused index load and mv are retained. Endpoint [0,3,0,4,0,1] has VL512/start256;
each call still checks all1024 output elements. The original recovery173
stopped tuple remains unknown. This is not full2688-child or Linux acceptance.

## e8-Specific Strict Gate

Actual target308fbc57 is vi31 with unsigned immediate31, not vx31.
a1 must point to ordinary indices; a6/t3 must remain0. Actual original-source
input31 is177, while input0 is185. The checker imports the accepted e8 model,
not an e16 or ei16 oracle. Input and ordinary indices/output are bytes;
indices16 initialization remains16-bit and is still checked in full.

Every call requires all4226 setup values, exact actual arguments,13 instruction
encodings/order, three vset returns, target VL/start/scalar,66 zero returned
vstarts across scope, and1026 distinct actual scalar **LBU** output/guard reads.
The original CTRL store must exit0; any subsequent retirement must be the
original a001 park. Park validation, as in the sealed contract, does not
require a minimum number of post-exit rows.

Generic CSV and strict prefix checks must agree on full trace counts.
Both raw logs require exact PREFIX66/BOARD/simulator success markers, with
explicit RVV_PERMUTE_DETAIL and failure veto even after PASS. No partial
oracle, missing tail, wrong pointer or halfword-result substitution is accepted.

Host distinction points (checker indices include the leading guard):

| Call / element | Correct | Injected error |
| --- | --- | --- |
|18 /0, VL1/start0 |177|vx0=185; incorrect source>=VL zero|
|66 /511, VL512/start256 |177|signed-immediate/OOR zero|
|49 /2, VL3/start1 |177|ei16 dynamic input1023|
|33 /0, VL2/start1 |91|prestart overwritten177|
|18 /1, VL1/start0 |91|tail overwritten177|
|42 /1, VL2/start1, sparse mask |91|inactive overwritten177|
|66 /1023, full-cap tail |91|missing scalar oracle read|

Host40 also covers both guards, returned-vstart, wrong encoding/vx encoding,
indices16 pointer, RNG/missing source byte, missing/truncated oracle, CTRL/park,
image/ELF/plan/budget drift, late abort and pending signal publication.
The real frozen monitor receives an authentic partial RVV_PERMUTE_DETAIL
from a plain Python child with no newline/final FAIL, and must stop it within5s.
Synthetic Host protocol fixtures are not DUT or replacement source evidence.

The final plan check is the same disk SHA plus fresh read/validate contract as
e16 vi31, factored into terminal_plan_gate solely for a direct Host mutation
test: changing the disk file after an initial read rejects before validation.

## Bounds and Ownership

M6 image only; jobs1/case9000s/direct service10200s, seed1, +NO_FSDB,
no UCLI/coverage, no retry. Private exact ELF, command, inputs, raw logs and
complete CSV remain required. First failure stops the owned process group.
Strict validation cannot publish PASS after abort; run.json must be COMPLETE
with exact PASS1 membership. Terminal rechecks actual disk plan, image and
approval pins. Service MainPID/cgroup, RuntimeMaxSec10200, KillMode control-group,
Restart no and trusted explicit UID bus are required on authorized run only.
Host service checks are mocked; service exit is not inferred from defaults.

Reference2621149 retired at273/s =9601.28s; +20%=11521.53s exceeds3h and the
9000s case bound. The bounds are unchanged. Parent reports a distinct M6 e8vx
run took4052s for about2.672M retired; that observation can inform a later
one-time parent budget decision but is not independently remeasured here and
does not guarantee this vi31 case completes. No automatic budget adjustment.

Runtime admission checks cap24/memory>=32GiB. reserved-slots counts unused
external reservations only, not already running processes. Prepare has no
live resource snapshot and performs no process/service query.

## Commands and Parent Gate

```sh
python3 -B test_host.py
python3 -B replay.py prepare \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --reserved-slots 0 --authorize-prepare
```

prepared01/plan.json pins exact source/reference/audit, Host evidence, M6
image/source/configuration/executable and imported helpers. ready.json contains
the plan SHA and service command with unresolved approval placeholders.
Preparation does not create a service. Independent runner review must finish
before separate parent authorization; source acceptance alone is insufficient.

The future parent review must bind:
```json
{
  "decision": "AUTHORIZE_E8_VI31_PREFIX66_ONCE",
  "plan_sha256": "EXACT_PLAN_SHA",
  "unit": "ara-gather-e8m8-vi31-prefix66-m6-01.service",
  "budget_risk_accepted": true,
  "reference_ready_sha256": "b15c7b86fa273aacbc464dca171a3cee3bc4140e701ed639ef70d7cc9aee5388",
  "source_review_sha256": "0fbf49c49a1570f57c2937b99854b253b265be5a606256dc47c53177ee9d43e4"
}
```

Run additionally requires --authorize-run, exact --plan-sha256 and pinned
--parent-review/--parent-review-sha256. Missing approval rejects before
admission or simulator launch. No approval or DUT acceptance is fabricated.
