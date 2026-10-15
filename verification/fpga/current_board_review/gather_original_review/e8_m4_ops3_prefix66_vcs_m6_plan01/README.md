# e8/m4 VI31 Prefix66 M6 Worker Code Preparation

This directory alone is owned. Old source models, helpers, scripts, RTL and
evidence are sealed and untouched. No VCS, build, Spike, service launch or
diagnostic replay is authorized by this preparation.

## Exact Scope

Historical source: `rvv_permute_restart_e8_m4_ops3`.
Runtime testcase and `+TESTCASE`: `gather_prefix_e8_m4_ops3`.
Original first66 natural calls,65 predecessors, endpoint `[0,3,0,4,0,1]`.
Actual vlenb128, m4/VLMAX512, physical predicate128 bytes (upper64 zero).
All512 scalar output bytes and both guards checked on every call:
33792 results,132 guards,33924 LBU oracle reads,66 returned vstart0 checks,
858 original helper instruction retirements. Each call's full initialized
setup is2178 values/2690 bytes. No claim for unused1024-array tails.

The source model supplies scalar semantics, not a substitute result artifact.
The checker validates actual retired PC/code, arguments, setup memory, m4
helper encoding, immediate31 (not scalar0), prestart/inactive/tail preservation,
two actual vlenb128 reads, one actual capacity512 return, and exact zero CTRL
exit followed only by original park. Raw logs require exact runtime oracles;
PASS text does not override FAIL/DETAIL/TRAP/ABORT, even partial markers.

## Prerequisites Remain Separate

Old READY SHA `f090f0d597b9e35a101a1f018a93ca9f61a04349c4243724f5c55e97094a7649`
is preserved historical evidence, not the current independent acceptance gate.
Main supplied actual READY02 SHA
`11aec353de588baa6981aa0e46757b76efdbcf7c0656585d5174e96aca523ebc`
and byte-identical Buildroot14.3 proof SHA
`7cc7582e71120bce71e5c29de897c271330ce0fa7a5c32dd6dad97dfb5c9cddd`.
Main subsequently supplied the actual accepted independent report SHA
`3a9c52768d5244fdc803779ee58744fa243e6946bdddfd953b574d62b0942a4d`,
REVIEW SHA `08bc0bd468973c644ff9e1d9ea7bfb0cba05038dd4063a60953fd1c1c0f02965`,
and actual execution SHA
`a4197c537a19076dc24f701a16ed0eec28d261ef506e3603c689c93345bc79cf`.
The gate binds the completed report's real schema:66 call records, unchanged105
input pins, one full raw parse, original proof SHA and exact m4 counts. Execution
records actual child1566733/rc0/no timeout/35.552925s/retries0, with pinned auditor
command provenance. No independent raw audit is re-executed here.
Host02 is retained as failed ENTRY evidence: it compared two different artifact
hashes, reference.json versus the raw commit log. Main subsequently identified
the frozen parent's generic postcheck occurring before its result return.
Both code blockers are addressed in the Host03 successor. Prepare is held until
Host03 PASS and independent ENTRY re-review. Parent plan-SHA run approval
remains unresolved; a prepared plan is not authorization to start a service.

## Future Worker Contract

Exactly one testcase, jobs1, seed1, fixed5400s case and6600s outer cap.
Source reference retired1353294;600 retirements/s is only a throughput proxy
(about2256s), not a completion guarantee. No retries or adaptive timeout.
Runtime admission counts external live simulators plus unused reservations,
requires total<=24 and available memory>=32GiB, and is checked again at dispatch.
The systemd service must directly own the worker (MainPID=self, matching cgroup,
KillMode=control-group, Restart=no, RuntimeMaxSec=6600). No short launcher that
detaches children. No FSDB, code coverage, UCLI or extra diagnostic runs.

Immediately after the actual monitor returns, before the frozen runner reads
console/run logs, validates its trace, or checks its inputs,
`child_outcome.unvalidated.json` exclusively records numeric rc/elapsed/timeout/
failure_seen and the exact runtime/private-CWD command, with file and directory
fsync. It requires no command metadata lookup. The worker installs a local
engine monitor hook for its sole testcase and restores hooks on exit; frozen
files are not edited. `runner_result.unvalidated.json` is a different secondary
classification record and can contain None for the frozen runner's timeout
classification, without overwriting the actual negative numeric wait outcome.
Command metadata provenance is a separate later durable record. First cause is
write-once and propagated to the terminal failure, not replaced by a later
metadata error. Sticky abort, exact COMPLETE membership, late disk-plan/image/
source pin checks and final pending-signal veto all apply before publication.

## Host Only

`python3 -B test_host.py` writes fresh `host03.json`, retaining `host01.json` and
the failed `host02.json`.
It runs generated scalar protocol fixtures and mocked worker/control gates,
plus the actual frozen M6 parent's _run_test with only its monitor function
replaced by a synthetic tuple. Tests force real generic console, trace and
input checking exceptions after monitor rc0/17 and an actual timeout
classification with negative wait rc. They pre-stage the private input copy,
never call build/run or take any frozen-tree build lock. No simulator, compiler
or reference engine executes. Host temporary files stay in this directory.
Host PASS is not DUT PASS, accepted plan or parent launch permission.
`prepare` requires the exact actual READY02 and independent report path/SHA;
its first invocation is durably recorded, and any preflight rejection is saved
without retry or loosening gates. The optional one-case `dryrun` bypasses the
runner's build method and only writes its exact runtime command and DRY_RUN
metadata, never invokes VCS or a compiler. `run` additionally requires a new
pinned parent review and direct systemd service identity. Consumed files freeze
once the actual plan has been prepared; later changes require a successor.
