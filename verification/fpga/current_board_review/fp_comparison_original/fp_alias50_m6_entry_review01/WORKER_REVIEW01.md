# FP Alias50 Frozen Worker Review

Decision: **BLOCK this worker plan's launch/acceptance.** One concrete runner/checker mismatch found; source/reference input ENTRY remains valid and unchanged. No reviewer DUT/Host/reference/build execution, no reference/CSV read, no sealed producer edit.

## Blocking Finding

`fp_alias50_vcs_m6_plan01/checker.py:52` requires one exact `BOARD_CASE_BEGIN alias_v8_e16m8_prefix50` in each raw console/run log. The accepted source `fp_alias50_m6_prepare01/prepared01/soc/alias_v8_e16m8_prefix50_main.c:4` emits only original RVV_FP_COMPARE_PASS50, BOARD_CASE_PASS and BOARD_REPLAY_PASS. It emits no BEGIN. Runtime sources and frozen hardware/tb search found no producer of that BEGIN marker; the actual accepted SoC ELF SHA4496c2... contains CASE_PASS/REPLAY_PASS strings and **no BOARD_CASE_BEGIN string**.

Consequently a correct firmware/simulator result is rejected at `checker.py:55` with `Missing/ambiguous original oracle BOARD_CASE_BEGIN` before this checker's full CSV oracle. This is an entry/checker false-negative, not evidence of RTL/numerical failure.

`test_host.py:test_console_veto_identity_and_full_count` manually adds BEGIN to its synthetic positive text. Thus Host02 nine PASS does not test the actual accepted firmware's marker contract and misses this defect. No software/source change or extra DUT trial is needed to prove it.

Preserve sealed plan/code/failed Host01 and any run records. Minimal successor: adjust only the console contract to the accepted ELF's real three firmware markers, preserving exact single50 count/runtime identity, Core Test SUCCESS, $finish, contradictory failure/DETAIL/trap/abort veto and the complete numerical/retirement/pin gates. Add a focused positive using the actual wrapper's marker set without invented BEGIN, retain missing/duplicate/wrong-count/failure negatives, then freeze a fresh plan/output for Main review. Do not add BEGIN to the sealed source ELF, recompile it, rerun reference, widen timeouts or edit old sealed checker.

## Reviewed Frozen Identity

- Worker READY: `8e020a10e4abe0cc6df26282941d32ee19c22e429f969052688ed2a96006134f`.
- prepared01 plan: `7f3fd75edda8e62f1de0dbb6141771d66fe8d8732fb70ad59a29b46b58976036`.
- checker.py: `5b17f2e86235cd90a7fd31a2226547e23d5e76839306a98c9b1e8107d10ebe83`.
- replay.py: `2ebd311bceffa7062a6e4dd48d691f69fe75a777c422211d43bad7a1d25f9aa6`.
- dut_strict.py: `1506ba9899a066b4e8072ffb2f82cd2f48df317f7e7be6eeaff80f9386e0cb9b`.
- Host02: `142405c3d19233450f8ea131f5cf7974bdaf8cba8df265c737aac430dc10c4ae`, reported9 tests/0 failures/0 errors,43.592809s. Host01 remains FAIL_HOST(5 failures/2 errors), not reclassified.

751 plan pins:750 nonraw files match; one292111-byte Spike raw log not read/rehashed. READY metadata and single dryrun command pins match. Actual source ENTRY556223..., REVIEW8462f1... and recovered receipt4754dcb... are bound, including checkpoint-only evidence, original outer1/offline0 and missing direct Spike wait/null elapsed. No promotion of inferred reference0 to durable wait.

## Other Scoped Checks

Static model keeps first50 ordered op0/unmasked e16/m8/CAP512,49 predecessors, complete25600 bits/100 guards/50 flags-vstart and original alias-source old bits/tail alternatives. Exact50×16=800 helper retirements,174 unused helper PCs, complete64100 initialization stores, actual parameters/source operands, CAP/vlenb,CTRL0/original park and six-event frozen generic protocol are retained. Source label is distinct from runtimeid. No independent full-reference retirement trace is claimed.

The private imported monitor template is correctly rebound to this scope and local monitored() before engine hooks; numeric tuple is durable before generic/metadata exceptions. Nonzero,timeout,FAIL,late abort,pin drift and sticky first-cause cannot PASS; fixed jobs1/case7200/service9000 and direct MainPID/cgroup/no restart/cap24/memory32GiB checks remain. Parent approval is separately required and bound to exact plan/ENTRY. No further blocker found in those scoped static paths; this is not approval of the currently blocked plan or proof of DUT results.

## Incident Boundary

The finding was sent immediately to Zeno/Main. Zeno then reported Main's authorized launch command was already in flight and that only its own `ara-fp-alias-original50-m6-01.service` was stopped, with disjoint receipts and old records retained. This reviewer did not issue a stop, query live processes or inspect that run's CSV/logs. Its actual DUT numerical outcome is not established by this static review; cancellation/entry rejection must not be attributed to RTL.

Static actual-ELF string evidence command exit0, chunk353953; full frozen plan/source-binding/pin check exit0, chunk8918c6. Source ENTRY/recovery acceptance is not revoked; only this worker's false marker requirement blocks release. No automatic retry/new authorization follows.
