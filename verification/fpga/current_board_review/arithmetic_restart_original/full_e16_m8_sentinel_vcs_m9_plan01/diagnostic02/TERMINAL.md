# Complete Closed-CSV Diagnostic, Not Full4095 DUT Acceptance

## Actual Execution

One POSTPROCESS_ONLY execution was admitted by the actual parent authorization SHA256 `6c7c6543887b681b866df27743d47a81f8063d720d5d972199475456c324d3e0`, exact ENTRY `f78626ca0bf1eb31e6a90f2c90fce0154a41ca89e88d594fe48314103dd3fb71` and Hilbert review `15a2b962badc7e70991a11fdceecf35dacdb8742cb145073935e41230849706f`.

Actual child wait0/348.59599893400446s, timed_out=false, retries0. The numeric receipt was saved before terminal result inspection. Diagnostic elapsed346.6951084039174s. The hard1800s budget was not exhausted or extended. Fixed /usr/bin/python3 resolved to the pinned Python3.9 executable. No DUT/reference/compile/image operation, sealed edit, old diagnostic overwrite or e8 runtime authorization occurred.

The sole binary open reached complete physical EOF:296607084B,2570844 records,2399641 retires. Stat dev/inode/size/mtime matched before/after and all80 consumed pins matched. Full CSV SHA256, calculated in the SAME semantic pass, is `1c8b5505754fdddad8b133f328ee511ef23370b46c76611f42c5bca80096503a`. No second raw scan/hash was performed.

## Semantic Scope And Endpoint

The full original4095 model and unchanged strict source/PC/helper/fresh/data oracle were retained. Fast sidecar changes were only those previously reviewed and differentially proven. Entire transport before/after digests match: `622226bd30e123a57baf1074731a730f4957c1488774ed3a0a2eae1c929ab9ce`; all2570844 records were delivered unchanged. No malformed tail was dropped.

- 3868 complete calls passed their full1028B output/fresh/source/oracle/vstart checks and required owner checks:1980416 result elements,7736 guards,498972 packed output reads,3868 returned-vstart-zero observations. Original source counters are checks3868/elements1980416/errors0. This is checked prefix evidence, not full4095 acceptance.
- Active original call3869 is seed2/op18/VL0/mode1/vstart0, helper `op_18`, next helper index3. It has no output oracle reads or returned-vstart result yet. There are227 unfinished source calls including this active call; none is silently waived.
- Helper counts are3869 for indices0..2 and3868 for indices3..12. All original RNG4416 store events were checked; no source exit was observed.
- Generic totals: arch42554, CVX request/response42553/42553, alloc/done21773/21770. Three uops remain at EOF, owners42551/42552/42553 (insns02055407/0205d807/02065c07); one unmatched architecture suffix is explicitly retained. Pending CVX is empty. Existing actual tokens remain strictly paired; EOF incompleteness is diagnostic-only, not accepted completion.
- Last valid record is a retire: cycle20211971, order2399640, PC80001d1a, insn0205d807. Recorded tail since last watchdog-progress event is0 cycles.
- Maximum observed watchdog-progress gap3280 cycles, retire gap3282, completed-owner lifetime3306. Every recorded million-cycle bin includes progress. This supports continued progress throughout the recorded prefix; it does NOT prove what happened after the last recorded cycle. Final simulator cycle is not independently known here, so a post-trace stall cannot be ruled in or out.

Result status is `DIAGNOSTIC_ONLY_PARTIAL_EOF_NOT_PASS`: physical CSV EOF is complete, while the DUT/source history is partial. `architectural_acceptance=false`, `whole4095_accepted=false`, and full-program finish was not called. Original DUT timed_out/rc255, producer NOT_PASS, original diagnostic01 internal-budget failure and accepted scope18/22 remain unchanged. No new RTL fault is established or repaired.

## Progress And Budget Evidence

Exclusive progress.jsonl has39 fsynced checkpoints, every65536 rows after complete after-digest/delivery, all rows==lossless_rows_delivered. The warmup baseline was37208566B at49.3556s (first checkpoint above32MiB). Later forecast rates excluded all earlier bytes/time, while total-finish estimates retained elapsed startup time.

Maximum predicted finish494.3258s; excess streak remained0, so the two-checkpoint1650s stop condition did not fire. Last checkpoint:2555904 rows/294868043B/343.9308s, predicted finish345.9190s. EOF was then reached without another scan. The observed348.6s is this execution's actual outcome, not a universal600s guarantee or a claimed interpreter speedup; the prior short timings and failed predecessor had different workload/host conditions and are preserved unchanged.

## Small Evidence Hashes

- `execute_wait.json`: `b71fb5d7960bbafb95d33a3a2860b064003607fb45a9d45326c11399a8e52d73`.
- `run01/result.json`: `6d7e7a01b8ba9a57445e13c0cb4b8cb63a9d5a1c86e3959d469c3631c8d617e0`.
- `run01/progress.jsonl`: `42782c7de0d1b33555f6e2fa3c12d63d5fafe3a1d3f9ed73930d7f71aa469251`.

Hilbert terminal review consumes only these small receipts/result/progress and pinned metadata, not the raw CSV or reference. No retry or further execution is implied by diagnostic completion.
