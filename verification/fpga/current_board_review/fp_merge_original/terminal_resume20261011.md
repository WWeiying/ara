# FP Merge195 Independent Terminal Review

Review date: 2026-10-11 UTC. Read-only reanalysis of existing artifacts; no
simulation, compiler, RTL edit, helper edit, or sealed-input write.

## Verdict

ACCEPT the recorded M4 architectural result for the exact original op0
195-call prefix. The complete actual CSV was independently reread using the
pinned generic trace validator and original195 checker; the recomputed audit
equals the recorded audit, not merely its PASS label.

Historical systemd service exit is NOT independently established: the unit has
been collected, and journal access is denied. Do not promote this report to an
unqualified service-terminal PASS using the default properties of a missing
unit. No architectural mismatch or failed oracle was found.

## Identity And Completion

- Plan: `candidate04_plan01/plan.json`, SHA256
  `c299582076496a50dbaa7a005c715f00a6a96b1d1e68c8f0438347cf72e1607c`.
- All757 plan pins verified before and after the CSV review. Frozen M4 image,
  source snapshot, compiled-source manifest and actual simulator files verified.
- Image ledger SHA256:
  `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
- Original Linux partition ELF SHA256:
  `d8abfc1bfebe188b1045a786e2ce17ba571e523c363b365ed28b805c99881710`.
  Read-only preparation audit rechecked115 pins, exact source provenance,
  original ELF reconstruction, prefix inputs and preserved oracle.
- Actual private SoC ELF SHA256:
  `01b9f6e58dec5ee13082e64211d23a37b94411d72051f517e3a0b46af479d124`.
  `inputs.json`, simulator identity, preload/testcase/trace command and cwd match.
- Parent review SHA256:
  `fea33b0b2c5d70377ce41cf7614f08d696006a9964f63abcceef828717e027cc`.
- `candidate04_run01/complete.json` SHA256:
  `f1c0b12850021a1822916f921a9ae3693db58790246167f313bdb70d0e83f20d`.
  Status `PASS_ORIGINAL_VFMERGE_PREFIX195_M4`, aborted=false,
  pins_unchanged=true, original_partition_complete=false.
- Runner COMPLETE, exact one result `fp_merge_prefix195`, PASS/rc0/empty reason;
  run and summary digests match completion. Elapsed4782.170085611753s <9000s.
  Both console and VCS log pass the strict original-marker/failure veto.
- Recorded/recomputed audit SHA256:
  `7553fae18bc0302cb783820c0a3a92bc2152045b2b7d69018ab2775b510d398f`.
- Actual CSV SHA256:
  `62a6c4b7aab855d1d27ad48f542246dfe95f9a082b783150263d4f657c352b7e`.

## Actual CSV And Oracle

3,377,573 rows; 3,370,004 retired instructions; cycles82..4,585,043.
1953 vector retirements,1953 CVX requests and1953 responses; zero CVX
exceptions or replays;855 backend allocations and855 completions.

All195 framed original21-instruction helpers and target executions match
PC0x800005e6/opcode0x5c805c57. Checks include actual VL, vstart, saved/restored
fflags, sticky flags, boxed64-bit scalar, packed returned status and one exact
zero CTRL exit store after all195 calls. First target cycle16490: VL0,
vstart1, sticky0. Last target cycle4569492: VL512, vstart256, sticky0.
All targets use boxed scalar0xffffffffffff0000.

The unchanged original firmware oracle checks all512 destination elements per
call, prestart/tail/masked state, both guards, scalar-result sentinel, vstart
and sticky flags. Its strict `cases=195 errors=0` completion is present in both
logs. CSV setup/status/target/exit checks and source/ELF identity complement
that full firmware oracle; this report does not claim a separate CSV bytewise
recomputation of every destination value.

## Process And Service Evidence

Unit: `ara-fp-merge195-candidate04-01.service`.
One current systemctl observation: not-found/inactive/dead, MainPID0,
ControlPID0, empty ControlGroup. No corresponding cgroup directory/tasks.
A full `/proc` inspection found no unit owner or matching worker/private-ELF/
trace argv path;1131 processes inspected without permission errors.

`PARENT_STARTUP.md` records parent-confirmed9600s/control-group ownership and
initial advancement, not final exit. Current missing-unit Result=success,
ExecMainStatus=0 and RuntimeMax=infinity are defaults, NOT historical evidence.
`journalctl --user` could not open journal files due to permissions. No
firstfailure artifacts exist in the run. Historical service-terminal evidence
remains the sole terminal-provenance qualification above.

## Remaining Original Scope

This is the authentic first195 calls, including all194 predecessor calls,
of the original e16/m8 ops0 partition of21504 calls. Remaining21309 calls are
not DUT-covered by this run. The historical printed completed194 is a
pre-call marker; the195th call is seed0/scalar0/valid-box/op0/VL512/mask0/
vstart256/sticky0. Other scalar patterns, seeds and invalid boxing are outside
this prefix's executed coverage. The full host model is not full DUT coverage.

No claim is made for the separate parent ELF, Linux execution/signals/tty/OS
timing, full original partition completion, or root-cause closure of the
archived no-retirement observation.
