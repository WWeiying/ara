# Independent Core Entry Review

Decision: **NO_BLOCKER_FULL6720_M9_ENTRY** for prepared01 plan `49ffb74caba23b096d9addb009511a4d92e21f51c9182379d839b345e53978a1`. Separate parent launch authorization and runtime admission remain required. This is neither a DUT result nor Linux closure.

## Source, Actual PCs and Owners

The exact accepted SoC ELF is `5242911cb3a64d2bab02be8babdad363d75796a5f25dd351b82706c6279aca7c`. Original order and all 6720 calls remain intact. Three actual helper starts are 0x8000065e, 0x800006ae and 0x800006fe, each with 21 original instructions. Their target PCs/codes are 0x8000068a/0x0c881c57 (ordered sum), 0x800006da/0x14881c57 (min), and 0x8000072a/0x1c881c57 (max). Capacity uses the actual three-instruction window at 0x80000656, with e16/mf4 vtype14 and capacity16.

The fractional source does not shrink destination coverage: each call stores a full e16/m1 128-byte destination, checks all 18 scalar output words including both 8-byte guards, and checks original flags/vstart. Aggregate requirements remain 967680 output bytes, 6720 flags and vstarts, 141120 helper retirements, and the original fixture/source/mask event counts. All helper PCs/codes and contiguous order are checked; other RVV instructions are rejected. Source events inherit the accepted source checker, with actual SoC relocation and actual linked ABI spills, not assumed Spike addresses.

Each helper performs five nonempty memory operations: seed load, old destination load, capacity16 source load, mask load at capacity16, and full destination store. Thus all 33600 memory owners are necessary even when the target VL is zero. Of 6720 targets, 5760 have nonzero VL and require an owner; only 960 VL0 targets are optional. All-masked nonzero-VL targets are not waived. The inherited generic observer retains all actual allocation/done pairs and CSR replay constraints; the per-call source ledger adds necessary-owner coverage rather than only aggregate balance.

## Runtime and Exit

The actual SoC exit is an SD of zero to CTRL 0xd0000000 at PC 0x8000006e; post-exit retirement is restricted to pure park 0x80000072/0xa001. No `tohost` symbol is assumed. Both raw console copies require exact success markers and reject DETAIL/FAIL/TRAP contradictions before acceptance.

The local engine hook is installed on the mature worker's actual run path. Its live diagnostic trigger waits for the complete original DETAIL line through expected_flags and newline, preserving the first diagnostic rather than stopping on a partial prefix. The actual monitor tuple is durably recorded before diagnostic reading or postchecking. Nonzero child status, timeout, failure detection, or postcheck exceptions remain failures; no retry is allowed. The final strict checker still rejects any DETAIL even if the live full-line trigger was not reached.

Prepared service is one direct worker, M9 image `48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`, jobs1, case10800/worker12000/service13200 seconds, KillMode=control-group, Restart=no, RemainAfterExit=no. No build or FSDB is requested. Runtime gates require actual service/cgroup identity, fresh output, exact input pins and parent approval, live capacity24 and at least32GiB available. ExecStopPost records actual systemd fields, then performs bounded metadata collection; it does not invent an outer exit from an internal PASS. Collector requires service success/exited/0, actual child0, complete scope, generic pairing, source-owner coverage, pins, raw marker veto and runner COMPLETE. Its own actual wait is retained separately.

## Existing Short Evidence

- Host15: actual exit0, 6.334799185860902s. Includes wrong flags/vstart/restore, full-output tail and guards, shortened BE, skipped helper/wrong code, bad backing initialization, missing freshness, wrong fixture bank, owner deletion and imbalance, actual ABI spill restrictions, EOF and numeric-first 0/17 preservation.
- Worker-hook Host1: actual exit0, 1.1694849720224738s. Enters the actual run/hook binding with a synthetic monitor, rejects every incomplete DETAIL split as a stop trigger, recognizes the complete line and base fatal, preserves numeric outcome before diagnostics, and preserves rc17 on diagnostic-read failure. This is Host control-flow evidence, not simulator execution.
- Prepare: actual exit0, 2.925871963147074s. Dryrun: actual exit0, 3.980798786971718s; exact M9 executable, runtime name, seed1, ELF, NO_FSDB and owned CSV command retained, with no DUT output.

Small actual receipt/log hashes, plan identity and nine local code/test pins were independently checked. The plan has 818 inputs; full pin verification is performed by the prepared worker. Accepted reference raw identity is inherited through the independent terminal/COMPLETE/result chain, not rehashed in repeated worker pin checks. No reference, Host, compiler, DUT or large raw parse was rerun for this review. No blocking findings remain in the bounded review scope.
