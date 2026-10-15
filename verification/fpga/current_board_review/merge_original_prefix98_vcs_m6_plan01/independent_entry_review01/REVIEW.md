# Independent Frozen Merge98 Entry Review

Decision: NO_BLOCKER_FOR_PARENT_CONDITIONAL_LAUNCH. Reviewed the actual frozen
plan and completed preparation artifacts. This is not DUT PASS or launch
authorization. Parent exact-plan approval and runtime resource admission remain
required. No sealed file, source, RTL or reference was changed.

## Identities

| Artifact | SHA256 |
| --- | --- |
| prepared01/plan.json | f97d3e2a933bfde527b1dd06b54f0055cb1bc2fca103d97308b1d0d45104b079 |
| prepared01/ready.json | fdeddeed08383bb993f28599f1141f860ba48aaf1fa07bf4b614c0ddd0f58149 |
| checker.py | 68ea8fac710500f9dda01606b4c633d91d09fdf1c75d6db766e316b7dfd01683 |
| replay.py | fba6b7d84d530d0b7a40e2ac25ae99231970a610aeeb34020cfc9dd2a13b7942 |
| test_host.py | 20680cfba425c953157ea26befa6790f02e7e571a96dba1696d3a25e12b3085b |
| host02.json | 5bb5e6e8b6ace30bbf29676f158c4678a9403e463c15efd61564dad0972c26bc |
| reference admission.json | e4b71f9ce87aa77eb7b28db1b727164f6e52a28bd37acac070c41e790bb9ed75 |
| reference REVIEW.md | 7790c94990664706b86513c3508fa74f392942d861ba17b3cf1eb7a2dd3a4dd5 |
| reference audit.json | 63ec9e40827c334f849a1d8d64a6dad3ab52d07ed8b1236c8f7f9a9477b9072f |
| SoC ELF | 4e495abc1ec6b553554c5ddee992db88234c969adcba2f92b90ed6c78ea245ab |
| M6 image ledger | a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0 |
| independent check_scope.py | 71797d40c7cfad9d0660691dee05d6b23724644fccc233a6d367b6012afb6c84 |
| independent scope_evidence.json | 819e067267acd0af8f06c37c733aefb3663a9cbee89d650ce13025167b488684 |

All725 plan pins matched independently before and after the added controls.
Verified complete transitive inclusion of reference baseline29, owned73,
independent audit97, and all three admission-named evidence files. Duplicate
paths agree. Actual admission decision is ACCEPT_SOURCE_REFERENCE_FOR_DUT_PLAN_BINDING_ONLY,
with empty blocking findings and dut_launch_authorized=false. The runner checks
the actual schema, exact counts/ELF/READY and audit status, not a pending draft.
The source reference remains a separate acceptance; no raw-reference reparse.

An independent ELF64 PT_LOAD reader matched all846 instruction PC/encoding
entries in the prepared specification directly to SoC ELF bytes. Original13
helper encoding sequence and source proof remain pinned. No objdump or ELF
execution was needed for this check.

## Exact Architectural Scope

All98 original calls and97 predecessors are required in order; original filtered
op0..3 history is checked at each selected call (3584 skipped iterations first).
All13 helper instructions must retire consecutively98 times. Each next call
requires the previous complete scalar oracle and full new predicate/output
setup. Interior helper execution outside its window is rejected. All20 unused
helper full PC ranges are forbidden, not just entry or vector-target PCs.

Every retired PC/code must match the actual ELF. Exact RVV counts cover nine
RVV instructions per merge helper x98, plus one capacity vset (883 total).
Legal vector-CSR instructions are separately recognized by the generic CVX
validator and strict CSR/window checks; their transport is not omitted.
Capacity executes exactly three consecutive instructions once, returning512
from original AVL=-1. Five startup CSRs and two vlenb reads are exact ordered
sites; unlike the reduction single, merge source places capacity between the
first and second vlenb reads. Both return128. Bootstrap CSR operands are checked.

Full original RNG/source/index/indices16/predicate/output setup stores and byte
enables are checked. Oracle is all50176 result HALFWORDS plus196 guard halfwords,
50372 ordered LHU comparisons, not only active elements and not50176 bytes.
Merge selector1 takes indices[i] fromv16; selector0 takes input[i] fromv8.
Selector0 is not masked-off preservation, and there is no gather OOR-zero rule.
Prestart and tail preserve0x005b. Actual pointers, unused scalar move0, requested
VL/start, original vset returns, returned-vstart0 and full store pointer remain
strict. Last call is VL512/start256/mask0, tuple[0,4,0,6,0,1].

## Host And Independent Controls

Stored Host02 has13 test methods,24 trace-negative subcases, zero failures/errors,
67.457s. All method names match current code and successful log entries; script
SHA matches. Host01 remains pinned failure evidence: its positive synthetic CSV
omitted legal vector-CSR CVX requests (1082 retired-vector versus883 requests).
Current fixture uses frozen is_vector_instruction to emit those events. This
is a synthetic transport correction, not a weakened oracle or a DUT retry.
Host02 directly records test-script SHA; checker/runner identities are supplied
by the frozen plan and handoff, not a separate Host imported-module manifest.

Executed only five small independent synthetic controls in this new directory:
the full98 positive, then insertion after the complete last oracle of an unused
helper vector target, another selected merge target, capacity interior vset,
and the original vlenb CSR. Every CSV passes frozen generic transport validation;
the positive passes strict with50176+196 checks, and all four extra-retirement
cases are rejected for their exact scope/phase errors. Each mutation preserves
the full positive oracle and inserts matched CVX events where applicable.
Results are in scope_evidence.json. Synthetic141786/141787 retirements are NOT
actual firmware/DUT counts. The producer Host suite was not rerun.

## Raw Failure, Completion And Publication

Both console and raw VCS log require exact singleton original/wrapper/simulator
markers and finish. Failure/partial DETAIL/trap/abort/parent-marker vetoes remain,
including the stored real child-process partial-line monitor test. The runner
uses the augmented failure monitor and a shared sticky cancel event; strict
exceptions/non-PASS latch abort, and cancellation during checking becomes
CANCELLED. One-case COMPLETE/PASS/rc0, exact summary, private ELF/image/command,
generic trace and strict trace count agreement are mandatory.

Success exit is the actual SoC sd at0x80000072 to0xd0000000, mask255/data0,
after full98 oracle completion. Only original no-effect0x80000076/a001 park
may follow. This is not reference HTIF value1 or its different park address.
Terminal checks freshly hash/read the disk plan and recheck pins/image/approval;
additional plan hashes follow expensive checks and result-evidence hashing.
Publication blocks SIGINT/SIGTERM and checks sticky/pending abort before and
after temporary serialization, then atomically renames. The final pending-signal
snapshot is the decision boundary; signals arriving after that snapshot are
not promised to revoke an already-made terminal decision. Expensive checks do
not run inside the blocked-signal publication section.

## Dryrun And Future Command

Stored dryrun run.json is DRY_RUN with exactly one named case, jobs1,seed1,
timeout9000, commit trace, coverage/probes disabled. Command uses frozen M6simv,
original source SoC ELF, +NO_FSDB and case-specific CSV; null returncode and
zero elapsed are dry-run metadata, not executed simulator success. Real run
uses and validates the frozen runner's private input.elf. Named RunOptions
sets skip_build=True, explicit simv, build_only=False; no build path is needed.

Dryrun evidence SHA256:
- dryrun_check.json: b6fc6c30bef799230c8d180bc8e01cc6b03ab1d79adb671f12a68ffdd80e679f
- dryrun/run.json: c211d99b0203d6011fad351f130818134b97ea5a1689324fafb8046c2b59f6ec
- dryrun command.json: 80fe4a8fd5884b33fd2984f31ff03a1dfc0aa621aca38e58968e278ebc99cb6f

ready.json emits systemd-run directly owning /usr/bin/python3 replay.py run,
unit ara-merge-original-prefix98-m6-01.service, RuntimeMaxSec10200,
KillMode=control-group, Restart=no, append logs and exact plan SHA. No shell or
detached intermediary worker. Parent review path/SHA remain deliberate unresolved
placeholders; preparation is not authority to launch. Worker requires direct
MainPID/cgroup and exact active unit/bound using explicit trusted user-bus env.
Fresh launch.json/replay paths enforce no retry. jobs1/case9000/service10200,
no FSDB/build. Runtime cap24/32GiB and unused reservation roster remain parent
admission work; no current capacity or service state was queried here.

Budget2020160/273 with20% margin is8879.82s, close to9000: bounded proposal,
not a runtime guarantee or automatic extension. Even a future DUT PASS covers
only98 of2688 calls, not later2590, all VL512 combinations, original Linux,
other merge records or the unknown historical stopped tuple.

No DUT, Spike, compiler/build, live query or shared-helper edit. Only this new
review directory was written; all sealed inputs remained hash-identical.
