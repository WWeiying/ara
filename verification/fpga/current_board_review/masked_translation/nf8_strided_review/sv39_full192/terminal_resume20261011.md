# NF8 Full192 Independent Terminal Review

Review date: 2026-10-11 UTC. Existing completed artifacts only. No simulation,
compiler, RTL edit, sealed-input edit or helper modification.

## Verdict

ACCEPT all192 source-derived M4 architectural scenarios in the exact48 groups.
Every actual CSV was reread through the pinned incremental oracle, and every
recomputed analysis equals its group completion and campaign aggregate after
normalizing JSON object keys. This is not acceptance based only on PASS labels.
No architectural mismatch, failed oracle, timeout or firstfailure was found.

Historical systemd service exit remains NOT independently established because
the unit was collected and journal access is denied. This is a qualified
architectural-result acceptance, not an unqualified service-terminal PASS.

## Verified Identity And Metadata

- Plan: `vcs_jobs8_plan02/plan.json`, SHA256
  `28785e754a948e29381f3c68faa1cbb3c0f393d7bb195d0b192b973606aa56b4`.
  All726 plan pins verified before and after full reanalysis; frozen M4 files,
  source snapshot, compiled-source manifest and actual simulator membership
  verified before and after. Plan and parent-review hashes match worker.json.
- Image ledger SHA256:
  `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
- Original Linux ELF SHA256:
  `c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282`.
  Original C/generator provenance and regenerated archived assembly verified;
  original192 geometries independently reconstructed without substitution.
- Existing completion SHA256:
  `e022b6d21aa827276d7ed6af6cdd9d4226aae1e65645ae3b64d72b4796f50fb9`.
  Recorded status `CANDIDATE04_NF8_FULL192_PASS`, firstfailure=null,
  post_hashes=UNCHANGED, orchestration=deadline_cancel_successor02.
- Exact48 group membership; all runner metadata COMPLETE, one PASS per group,
  timeout2400s, jobs1, seed1, private input snapshots and commit trace enabled.
  Recorded runner elapsed929.473285..1700.147960s; group elapsed
  941.565871..1717.124854s, below2400/2520s respectively.
- Pilot acceptance precedes remaining47 runner intervals; observed maximum
  interval concurrency8. Worker start2026-10-11T11:21:39.263842Z; last runner
  completion2026-10-11T14:02:03.574215Z, delta9624.310373s <18000s.
- No firstfailure artifact under this run.

## Complete CSV Reanalysis

All48 actual CSVs, totaling5,137,924,175 bytes, were parsed without launching a
runner or simulator. The offline audit completed in1238.881803s with exit0.

- Exact trials0..191, four per group, no missing or duplicated member.
- 45,109,528 retired instructions with continuous per-group order and
  nondecreasing cycles.
- 594,288 original/reference-ledger comparison calls, all got=want, with
  independent expected values and exact comparison order.
- 11,193,408 checkpoint byte comparisons, including the full8192-byte backing,
  gaps, physical register tails, neighbors, guards, inputs, masks, output,
  page tables, trap records and restored CSR state.
- 144 expected page faults plus192 S-mode return ecalls =336 handler records.
  Each trial's entry/fault/checkpoint/PTE/SFENCE/retry/target/younger/return/
  completion order matches its expected fault or no-fault path.
- NF8 target PCs and instruction words, original stride/base/mask geometry,
  fault cause/PC/permitted tval/vstart, unchanged-PC retry and active-prefix
  poison are checked. Implementation-permitted partial store fields remain
  constrained to original or correctly stored values, never arbitrary bytes;
  Spike field order is not imposed on DUT.
- Every group has its complete case/check counters, completion magic,
  zero error/unexpected state, and exactly one zero CTRL exit.
- Each private ELF hash/source/path, actual image metadata, exact simulator
  command/cwd, runner metadata, COMPLETE/PASS/rc0/empty reason, both console
  and VCS-log success/failure vetoes, and elapsed limits were checked.

Raw evidence map digest:
`1baf2c91b15f8c80363144b1d962cde0eadc18d3132404db7222e4096a133683`.
Recipe: SHA256 of UTF-8 `json.dumps(mapping, sort_keys=True)` with Python's
default separators. Mapping contains480 relative-path-to-SHA256 entries,
relative to `vcs_jobs8_plan02`: for each `groups/groupNN`, `complete.json`,
`command.json`, `run/run.json`, `run/summary.json`, and under
`run/tests/nf8_gNN`, `inputs.json`, `input.elf`, `command.json`, `console.log`,
`commit_trace.csv`, `work/run.vcs.log`. Each digest was calculated from the
reviewed raw file, not copied from the campaign's PASS record.

## Process And Service Qualification

Unit: `ara-nf8-full192-candidate04-01.service`.
Current one-shot service observation: not-found/inactive/dead, MainPID0,
ControlPID0, empty ControlGroup. No corresponding cgroup directory/tasks.
Full `/proc` inspection found no unit owner or matching worker/private-ELF/
trace argv;1131 processes inspected without permission errors.

The unit has been collected. Missing-unit Result=success/ExecMainStatus=0 and
RuntimeMax=infinity are defaults, not historical service-terminal evidence.
`journalctl --user` could not open journal files due to permissions. The pinned
startup observation proves actual18000s/control-group ownership at startup,
not successful historical service exit. That final service-exit qualification
remains open unless a historical terminal snapshot is supplied.

## Scope And Remaining Work

The acceptance is all192 original source-derived NF8 positive-stride
Sv39 scenarios in48 independent four-case ELFs: unmapped0/1, store0/1,
boundary1/3/5, masksff/aa/24/00, gaps1/3, split0/1;144 faults and48 alloff
no-fault cases. It is not execution of the original Linux ELF or one continuous
192-case Linux process.

Linux SIGSEGV delivery, ACCERR/MAPERR siginfo, signal-frame/context handling,
OS scheduling and original169/later128 error localization remain unverified.
The full192 architectural result does not localize the historical169/later128
error reports or establish an original Linux failure's internal cause.
