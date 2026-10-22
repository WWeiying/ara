# E8/M8 VI0 First112: Instruction-Bound Review

2026-10-11. Read-only evidence/source/ELF-disassembly review. Only this new report
is written. No reference, host test, DUT, build, live query, RTL change or old
script/output modification. The full112 goal is retained, not reduced to96.

## Decision

**A separately parent-approved successor reference with fixed5,050,000 steps
(+1%) is reasonable.** The observed cutoff is a deterministic debug instruction
budget in the final scalar oracle, not a wall/file-size timeout or measured
vector deadlock. Conditional disassembly accounting puts the remaining normal
success path at approximately2,737 instructions; a4,000-instruction envelope
allows counting slack. The proposed50,000 additional steps is ample for that
path without changing source, ELFs, target/history/oracle or DUT9000s.

This is a recommendation for one explicit budget revision, **not execution
authorization or PASS**. Keep the original NOT_COMPLETED_WITHIN_BOUND result.
Do not automatically append another allowance if the successor fails or reaches
its limit. All112 target instructions completing does not close the last
oracle, guards, status printing or architectural exit.

## Exact Observed Stop

Let `D` be
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/gather_original_review/e8_m8_ops2_prefix112_prepare01`.

The sealed `D/reference/not_completed.json`, execution/command records, debug
script, checker source and raw commit tail agree:

| Fact | Existing measurement, independently checked where noted |
| --- | --- |
| Stop status | NOT_COMPLETED_WITHIN_BOUND; instruction_limit_without_htif_exit |
| Debug script | `rs 5000000`, `str 80000d80`, `quit` |
| Commit count | Exactly5,000,000; independently counted from raw trace |
| Firmware retirements | 4,999,995; initial5 commits are boot ROM PCs1000..1010 |
| Simulator process return | 0, from debug quit; not a firmware success exit |
| Spike wall time | 8.440625923s, not120s |
| Raw commit size | 327,020,339 bytes, about311.9MiB, not768MiB |
| Calls entered / full oracles | 112 /111, reported by sealed checker |
| Helper counts | Each of13 helper PCs retired112 times, reported by sealed checker |
| Scalar output reads | 114832 of114912; last call946 of1026 |
| Last tuple | [seed0, op2, scalar-slot0, length6, mask3, trial3] |
| Final retired PC | 0x80000614, `addi s4,s4,1`, opcode0x0a05 |
| Resulting s4 | 0x3b2=946; **next** PC is0x80000616 |
| Actual error counter | Last x27/s11 write is0 at0x8000039e; no subsequent write |
| Actual completed-case counter | Last x9/s1 write is0x6f=111 at0x8000063c |
| Actual start / VL | x21/s5=1023; x25/s9=1024 |
| Architectural exit | No execution of HTIF store PC0x8000007a |

The read-only raw scan also found zero executions of the four error-increment
PCs0x80000520 (returned vstart),0x8000055a (result),0x8000063a (guard), and
0x80000696 (case count), and no trap_ records. Existing reconstructed console
and debug `str` show only `BOARD_CASE_BEGIN gather_prefix_e8_m8_ops2`.
Literal error-word search also found no hits, but scalar log-byte stores are
not readable messages by themselves: the error-register/control-flow evidence
and sealed checker's console reconstruction are the stronger observations.

I did not rerun the full semantic checker/model. Its111-complete/112-vector
acceptance is retained as recorded evidence, cross-checked against source,
raw endpoint/control-flow and fresh trace hash. This is not a new full-reference
acceptance audit.

## Why This Is The Instruction Bound

`D/prepare_prefix.py:227` emits `rs {MAX_RETIRED}`; the old checker declares
MAX_RETIRED=5_000_000. The actual script/command point to this run's own ELF and
log. `prepare_prefix.py:250` separately enforces120s, and RLIMIT_FSIZE separately
enforces805306368 bytes per file. Neither fired: execution.json records rc0,
not TimeoutExpired or SIGXFSZ. The75.97s preparation elapsed includes subsequent
offline auditing; it is not the simulator wall time or evidence of a timeout.

The local Spike `riscv/interactive.cc:269,404-429` maps `rs` to silent run,
parses the explicit step count, performs bounded `step(1)` calls, then services
the next debug commands; `quit` calls `exit(0)`. Source semantics are corroborated
by this exact5M-commit trace and the printed debug `:`. The source file was read
and hashed, but this review does not independently rebuild/prove its binary
provenance. The actual Spike binary hash is recorded below.

Important accounting distinction: `rs` includes the5 boot-ROM instructions,
whereas `firmware_retired` excludes PCs below0x80000000. The current checker
uses total_commits>=MAX_RETIRED to classify this incomplete endpoint, and an
independent firmware-count ceiling during parsing. A successor must bind the
explicit total-step limit and its compatible checker ceiling, retaining this
distinction rather than pretending all5M were fixture instructions.

## Remaining Oracle And Exit Paths

Disassembly is of the **existing Spike ELF**, not a new compile. `output` is
0x80003630. Last load at0x80000550 reads0x800039e2=output+946, value91, hence
result element945. The equality branch0x80000556 is taken to0x80000612 and then
the final increment retires. Both guards remain unread for call112.

Thus the80 missing oracle reads are precisely:

-78 result elements946..1023, at output+947..1024;
-left guard output+0 and right guard output+1025.

For the observed state, mode3 is all-off, start1023 and VL1024. Results946..1022
take the prestart bypass. Element1023 reaches `selected(3,1023)`, returns0,
and also expects91. No vector instruction or new helper call remains. The
existing checker already checked all1024 vector-store values of call112;
that does not replace executing its last scalar comparisons and guards.

### Normal Success Path: Static Accounting, Not Measurement

Assumptions: remaining loads/guards match91, no unexpected trap/state corruption,
and the shown ELF/control state is unchanged. Counts below count retired
instructions, including compressed instructions as one each, not bytes/cycles.

| Path | Disassembly boundary | Conditional instructions |
| --- | --- | ---: |
| Finish current loop tail | 0616,061a,061c | 3 |
| Remaining prestart elements946..1022 | 052c..0536 ->0550..0556 ->0612..061c | 77*12=924 |
| Last element1023 | additionally053a/053e/0540, selected0256..0278,0544 | 24 |
| Both guards, case increment, prefix exit branch | 0620..0642, skip063a | 10 |
| Summary call sites, including branch on errors0 | 0698..06f2 | 23 |
| Summary text/number callees | text027a, num0294, replay_write0160 | 1061 |
| Fixture epilogue | 0316..0332 | 15 |
| main success control and epilogue | 00cc..00ec ->00a6..00b0 | 12 |
| BOARD_CASE_PASS and BOARD_REPLAY_PASS output | replay_text00ee,59 bytes | 658 |
| Startup return and HTIF exit store | 0052 ->0068..007a | 7 |
| Total after observed stop | Through the successful HTIF store, excluding park | approximately2737 |

For reproducibility of the print estimate: non-full log gives `text(n)=22+17n`
instructions, `num(d)=34+28d`, `replay_text(n)=9+11n`. Summary literal lengths
are27/7/8/1; numbers8/112/0 have1/3/1 digits. The59-byte final BOARD text and
short existing BEGIN log are far below8191-byte capacity. There is no unbounded
UART wait in this Spike runtime: output is bounded RAM stores.

Use **less than4,000 additional instructions** as a conservative normal-path
envelope, not an observed exact completion count. This predicts total commits
near5,002,737 and firmware retirements near5,002,732; neither is measured yet.
HTIF-store acceptance is the checker's endpoint. Simulator/HTIF handling after
that store and process exit must still complete under the unchanged wall bound.

### Error And Noncompletion Paths

- A mismatching remaining result goes0556 ->055a, increments errors and may
  print DETAIL before continuing. At most20 details are printed, then the
  summary/return is FAIL. A generous per-detail envelope of4,000 instructions
  covers the bounded label strings, small numeric arguments and RAM output
  visible in055a..0612/text/num. A loose worst-case multiple-error tail can
  therefore exceed50,000 (roughly20*4,000 plus ordinary tail). **Do not promise
  the new cap guarantees completion of every failing diagnostic path.** The
  trace checker rejects at the first bad read; no larger allowance is needed
  to turn such a run into an accepted result.
- A bad left guard at062c skips the right guard and increments errors; a bad
  right guard at0636 also increments errors. Missing/mismatching guard reads
  cannot be accepted merely because a target passed. Summary selects FAIL at
 06a4, return becomes1 at06ee, main prints BOARD_CASE_FAIL, and HTIF value is3,
  not1. This bounded guard-failure tail is also well within4,000 absent traps.
- An unexpected trap has an explicit veto; no liveness envelope for arbitrary
  corruption is asserted. Missing exit/partial oracle at the successor's bound
  remains NOT_COMPLETED, even if its process again returns0 from debug quit.

The old parser checks actual arguments/setup/CSR/vector values/stores and
scalar reads while parsing; a mismatch raises ValueError, not the specially
caught ReferenceBoundExceeded. On successful exit it requires all112 calls,
all13 counts112,114912 unique scalar reads, HTIF1, exact success markers and
no FAIL/TRAP/MISMATCH/DETAIL. Its final raw-console veto is reached only after
exit, not in the bound-exceeded branch. This review's separate error-state
inspection is consequently important: NOT_COMPLETED alone is not an all-errors
veto certificate. The new successor must retain fatal mismatch handling and
must not catch generic checker failure as a mere budget event or PASS.

## Conditions For A Single Successor

1. Parent explicitly approves5,050,000 total debug steps once, in a NEW owned
   reference directory. Bind the old failed evidence and new policy side by
   side. No editing prepare01, its script, checker, metadata or result.
2. Reuse the exact Spike/SoC ELFs, complete adapted source, original source/ELF,
   helper bytes, runtime, fixture/model/oracle and original112-call history.
   Restart the same ELF from reset, **not** resume at the stopped PC or bypass
   the first111 oracles. No rebuild/optimization/change of target or setup.
3. The new orchestration/debug command and compatible checker budget are the
   only allowed policy delta. Record code diffs/pins and independent review;
   do not import the unchanged5M checker then suppress its budget exception.
   Keep all semantic vetoes and full terminal checks intact.
4. Keep120s and768MiB-per-file, no auto retry or second addition. Measured
   8.44s/327MB leave ample non-instruction headroom; +1% proportional estimates
   are about8.53s/330.3MB, not guaranteed bounds or RSS measurements.
5. Recheck hashes before/after. Success requires the actual final scalar
   oracle/guards, zero errors, all three exact success messages, HTIF1 and
   clean process termination. A future reference PASS is still not DUT PASS,
   full2688/Linux closure, or identification of the historical stopped tuple.
6. DUT case9000s stays unchanged; no DUT launch is requested here. Any later
   admission must independently assess the unchanged SoC ELF and execution
   budget. This reference envelope is not a VCS performance guarantee.

This is a transparent correction of a now-measured software reference step
allowance, not RTL/timeout tuning to hide a bug. The original5M result remains
valid evidence of an insufficient bound. If any pin/semantic change is needed,
or the new run does not close its full oracle within the one fixed allowance,
stop and report rather than automatically increasing the allowance again.

## Fresh Hashes

Paths below are relative to D unless stated otherwise:

```text
reference/not_completed.json 17c990964e9bcd4ba804ec1af5a950c1b88b5cbafc205ad61f9777bb91ee76f2
reference/execution.json 3ebb638d1b77e4f46b61d2fc7ebbb45d8df65d640e37e3301f771ba7482ff0ad
reference/command.json e2f98796cd9f13b4ce10cc138910be31691bfe9e8b8042e4155ae3e1742c8bc4
reference/spike.cmd 29eff40ebbd39d28b9b92c3c939a616a023727c6421413e3216d03de585c4bc2
reference/commits.log af0735ff3e02120d96dd93cd79f157a5ed754a62731a6f1a4ec5d0548fe7d5b3
prepare_prefix.py 8a1a2f28dc597cf9d35dd687eac67a6566ad9e2a081b9c025a907cf8dfe6854c
reference_check.py 3844f85c0dc0b4f423a3d24f3e1f88a16067e399f6e0742351b598c5fab844ee
source_elf_proof.json e84846e23d5320e6474a5e4876aebecb4c124067e593c7b51fff93bb459d80e1
spike01/gather_prefix_e8_m8_ops2.elf 93cfba245d048b057891ed94db7feacac71cd41a2076569de4d130c9917e0f78
soc01/gather_prefix_e8_m8_ops2.elf a0445bcb877799d488e40f37d7bcbc038d9f0e36a7a60e147ed8baf3c5ea5f74
prepared/gather_prefix_e8_m8_ops2/case.c 1caee836dd7af3bc5f33d4ce73ab906940e6b0d600960fa2a706f04a6f50bf41
prepared/runtime.c 91aecf556bf3f17f1e3b21241099c81fdca2e624eff3a1a37986dc9629dae5db
prepared/startup.S 3ab886ee55bf807790e0c17e982d3142e5207f317bbde593d2b5d8cc4f151582
```

Actual Spike `/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike`:
`c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2`.
Local `riscv/interactive.cc` under that project:
`a771004a13d72e1932b6e30336ae95a226316b7d7ac2727b687630f6d172fecb`.
These fresh identity checks are not a rerun of every baseline pin or a rebuild.
