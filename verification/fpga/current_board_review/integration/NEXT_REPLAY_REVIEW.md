# Next Replay Review

Review date: 2026-10-11. This records preparation checks, not DUT acceptance.
Production RTL was not edited during this review.

## Whole-register campaign

The20 partitions cover1134 distinct original configurations and retain366
explicit source exclusions. Full-program and partition Spike runs passed.
The six-worker service is active; independent startup evidence establishes
six matching ELFs on the frozen M4 image with advancing retire traces:
[startup review](../whole_register_original/startup_review01.json).
The service supplies the30000-second external deadline and cgroup teardown
required by the independent prelaunch review.

Partitioning does not preserve every predecessor vtype or the original
inter-operation execution history. Terminal partition PASS must not be
reported as continuous original-program or Linux acceptance.

## NF8 full192

The terminal software-reference status is `HOST_SPIKE_ALL192_PASS_NOT_DUT`.
The jobs8 driver was read through reference identity checks, host CSV gates,
image validation, per-group completion, pilot admission and aggregate checks.
Its CSV checker binds actual scalar observations to the original per-trial
oracle, checks trap/retry order and CSR restoration, invalidates stale memory
observations after vector stores, and requires completed comparisons and exit.
It is not a direct observation of every internal vector writeback.

An independent invocation of `test_jobs8.py` passed all9 tests, including
pilot failure, post-pilot evidence failure, cancellation, capacity accounting,
fixed scope and refusal before terminal references. Full48-group CSV checker
validation and ready-plan review are still prerequisites to DUT launch.
The intended service limit is18000 seconds, with2400 seconds per simulator;
its eight slots are reserved even while group0 runs alone.

## Arithmetic original prefixes

Reviewed plan:
`../arithmetic_restart_original/candidate04_plan01/plan.json`, SHA256
`34b4caf0f0810a3194449e58bc337b9cadb93d4a31847f70dc871b16c209e0b4`.
All17 replay-helper unit tests passed in an independent invocation.
The acceptance path requires exact markers, zero exit, raw failure veto,
actual private ELF/image identity and unchanged pins. It requires the38-case
M4 predecessor to finish successfully before admitting two new workers.
Use a directly owning service with10000-second runtime limit and cgroup
teardown; the plan's number alone does not enforce an outer deadline.
No prefix DUT launch was performed by this review.

## Capacity and remaining preparation

The coordinated reservation is NF7=2, current38=4, whole-register=6,
NF8=8 and Gather=4, total24. It is a coordinated roster, not a machine-wide
lock. Additional unreserved simulators must be counted at admission.
After current38 terminates, its four slots can support arithmetic-prefix2
and FP-comparison2, subject to each plan's independent acceptance gates.

Remaining75 Gather sources have host/Spike readiness, with accepted8 giving
exact83 unique single-source records. The full parent/stall sequences remain
separate obligations. Three FP-comparison prefixes contain682/130/130 calls
and have software-reference evidence; their DUT plan and budget still need
review. None of these preparation results is a new RTL PASS or a bug closure.

Parent read-only recheck: all75 SoC ELF contents match the prepared manifest
hashes, and the83 source identities are unique with exactly8 accepted and75
prepared entries. This count check does not replace review of the mapping from
each source record to its executable. All10 modified production RTL files in
the verification worktree also match the M4 frozen snapshot hashes; no source
drift was found in those files.

NF8 has conditional launch authorization after complete host validation,
ready-plan sealing and independent review without blocking findings. The
reserved unit is `ara-nf8-full192-candidate04-01.service`; it must own its
worker directly, enforce18000 seconds, use control-group teardown and append
logs. Its review binds Gather's future unit as
`ara-gather75-candidate04-01.service`. This authorization is not evidence of
launch or PASS. The Gather driver is undergoing a separate independent
review; no Gather DUT launch was authorized in this review.

Launch ordering: do not replace the predecessor38 reservation with arithmetic
or FP workers before NF8 completes its initial admission and the entire Gather75
campaign terminates. Gather rechecks its fixed reservations before every case;
initial admission alone is insufficient for releasing that reservation.
NF8 deliberately retains the exact old service's four-slot reservation even
after it ends; starting replacement services first would count those as other
workers as well and correctly refuse that unchanged reservation plan. Keep the
original roster through these gates, then use released slots under the
parent's coordination. Do not retry a refused sealed attempt or weaken the
capacity check to bypass this sequencing requirement.

## Blocking Review Finding: Late Timeout

Independent review reproduced a false-PASS race in the proposed NF8 jobs8
driver: a timer can set firstfailure during final checking after the simulator
exits, while the group still returns PASS and the aggregate ignores abort.
See[reproduction and required fix](../whole_register_original/nf8_full192_independent_review01.md).
NF8 pilot authorization is on hold until a successor synchronizes timeout and
terminal state, rejects any aggregate abort, passes race-negative tests and
receives independent approval. This is a verification-driver defect, not a new
RTL failure or evidence of a previously timed-out DUT passing.

The earlier selected4 NF8 and active NF7 adapters use the same pattern. Do not
edit the active NF7's sealed helpers. Its final independent audit must inspect
terminal service state, recorded abort and every firstfailure artifact rather
than trusting the aggregate status string. Any recorded timeout/cancellation
vetoes acceptance even when all group status strings say PASS.

Read-only selected4 check found `firstfailure=null`, no firstfailure files,
and group durations327.67..476.40 seconds, below their1950-second bound.
No occurrence of the reproduced timeout race was found in those results.
This observation does not make the older helper safe for future campaigns.

## Subsequent Verified Progress

The unchanged M4 selected38 campaign has terminal PASS with successful service
exit and independent1368-pin/76-log/38-private-ELF audit; see
[terminal audit](CANDIDATE04_38_TERMINAL.md).

The NF8 successor passed14 independent host tests, including actual timeout
threads and signal/publication cases. The code-only independent review found
no remaining blocker. Full48 CSV-checker validation subsequently reached
`HOST_CSV_ALL192_PASS_NOT_DUT`; final plan/pin admission remains separate.

Gather75's corrected startup/resource helper passed7 host tests and independent
3972-pin review. Plan SHA is
`116e89a3b9466ae910926653f1a84abb9c480c7dc12a9aca77ba81f5e76b2f83`.
The service `ara-gather75-candidate04-01` started and was confirmed active.
Its first-stage startup record identifies four real matching simv processes
with cycles599->942,425->771,369->713,195->540 in the bounded observation.
This establishes actual startup, not full75 completion. Prefix and FP workers
remain held until Gather terminal and NF8 admission as specified above.
