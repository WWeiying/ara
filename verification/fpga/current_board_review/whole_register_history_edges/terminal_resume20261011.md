# Whole59 Independent Terminal Review

Date: 2026-10-11 UTC. Existing actual DUT artifacts were read offline. No
simulation, reference rerun, compilation, RTL change, helper modification or
sealed-input write. Only this independent report was added.

## Verdict

ACCEPT the M4 missing59 original-adjacency supplement: all59 actual CSVs were
fully reanalyzed, and each analysis exactly matches its pair completion and
aggregate result. No architectural error, failed oracle, timeout, cancellation
or firstfailure was found. Exact count: **118 executed calls, not119**, plus
117 excluded tuples between the selected endpoints.

Historical systemd service exit remains UNVERIFIED. Aquinas separately records
the collected unit and unavailable journal; its default success fields are
not historical exit proof. This is acceptance of the actual architectural
results, not an unqualified service-exit attestation or continuous1134 closure.

## Frozen Identity

Paths below are relative to this family directory.

- Plan `successor02/preflight01/plan.json`:
  `9af488c58cef1ae4e76b171036a254b32814606f3659a4b36d09db89f1f10f81`.
- Driver `successor02/driver.py`:
  `39461b0782d8a744fd3e35737779a4e72e47df8b54b97a38b7c7423ec856f5e0`.
- CSV adapter `successor02/csv_adapter.py`:
  `8107496f63e320e369355ebe59e4e4601c61497a06ed8509dc1bc6debefb64cb`.
- M4 image ledger:
  `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
- Completion `successor02/preflight01/complete.json`:
  `fe5630198530fb30c3a96bdb45d9b614b7f279d7cadd442426dd6e5c64074bb6`.
- Actual parent authorization `successor02/resume02/review.json`:
  `ab1d2ab4d865e28dafd11c9e0cf3aeb37585c8567898fe54bf1205c29e5df4e3`.
  This is the actual review path, not `preflight01/review.json`.

All1381 plan pins and frozen image identity passed before and after the full
CSV read. Plan/review hashes match worker.json. The parent review's whole1134
strict acceptance, validation and independent-audit references match their
specified hashes; the preceding whole1134 campaign was not rerun or reaudited.

The current pair source equals the sealed original SoC port after removing
only the two-line ordinal-range selection guard. Original setup, input,
assembly and full oracle remain bound by the unchanged plan pins. No reduced
oracle or substituted ELF was used.

## Exact Original Range

Independent enumeration of the original loops gives1134 executed calls and
366 exclusions. Removing the adjacency already retained by the20 op partitions
leaves precisely59 edges:57 cross-operation and2 cross-seed edges. Plan calls,
executed IDs, order and intervening skips equal that independently derived set.

Executed IDs are zero-based in the original1134-call sequence, not raw loop
ordinals. The exact endpoints can be specified compactly as follows:

```text
A = [19,39,59,79,99,119,139,159,179,199,219,239,254,274,294,314,330,346,362]
For seed s in {0,1,2}, for j in {0..18}:
  pair(20*s+j) = [378*s+A[j], 378*s+A[j]+1]
Additional seed transitions:
  pair19 = [377,378]
  pair39 = [755,756]
```

Thus pair00 is19->20; pair58 is1118->1119. There are118 distinct selected
original call IDs and118 actual call executions. Each pair starts fresh;
the two calls within it run predecessor then successor, without restart
between them. Intervening excluded tuples total117, not extra target calls.

## Actual CSV And Exit

All59 actual CSVs were parsed, totaling462,604,890 bytes. The pinned adapter
checks every retired instruction against the accepted ELF disassembly, scalar
addresses/masks/data, full1024-byte input initialization and1088-byte old
destination initialization for each call, original arguments, predecessor
vtype, target order/PC/opcode, vstart before/after, returned status, preloads,
stores, all1088 ordered output bytes and guards per call, and original counters.

Recomputed totals:

- 118 target calls,236 whole preloads and118 whole output stores.
- 128,384 output-byte comparisons; no sampling or omitted prefix/tail/guard.
- 4,148,440 retired instructions with continuous per-pair retire order and
  nondecreasing cycles.
- Each pair's counters exactly `[2, its_original_skip_count, 0]`.
- Each pair has one zero raw exit and one zero CTRL exit.

For every pair, private ELF/source/hash, actual M4 image metadata, exact
simulator command/cwd, runner invocation, COMPLETE/one PASS/rc0/empty reason,
summary agreement and both console/VCS-log completion were verified. Additional
raw-log inspection found no UVM_ERROR, failed assertion, failure, timeout or
cancellation marker. All59 result memberships are exact; aggregate
firstfailure=null and post_hashes=UNCHANGED; no firstfailure artifact exists.

The complete offline review exited0 in112.969572s. This is audit time, not a
simulation runtime measurement.

## Runtime And Evidence Binding

Every runner elapsed time is strictly below600s and every pair elapsed time
below660s. Observed pair range104.635609..131.689629s. Maximum overlapping
runner intervals6. Last runner completion is1149.301548s after worker start,
below the3000s campaign bound. Recorded launch requests3600s,
KillMode=control-group, Restart=no and the direct frozen worker.

Raw evidence map SHA256:
`cfd603382a8c0228d6ce6b5865ab8f05f53e27bf8d0436d47445a258b0b767d7`.
Recipe: SHA256 of UTF-8 `json.dumps(mapping, sort_keys=True)` using Python's
default separators. The590 entries map paths relative to
`successor02/preflight01` to SHA256: under every `pairs/pairNN`, include
`complete.json`, `command.json`, `run/run.json`, `run/summary.json`, and under
`run/tests/whole_edgeNN`, `input.elf`, `inputs.json`, `command.json`,
`console.log`, `work/run.vcs.log`, `commit_trace.csv`.

## Service History And Residual Processes

Aquinas startup evidence `successor02/resume02/startup_observation.json`, SHA
`14a866a38d48fba01532664884f8e3a2574b952fd2edbb431cbd06b6f3d0b113`,
records parent-confirmed worker450565 and six private-ELF simulators, plus one
actual three-second trace-growth observation. It is startup, not final exit.

Aquinas `successor02/resume02/terminal_service_observation.json`, SHA
`19529d5af013c7aea9599f79cceb6bddb81e3b6cb2d53f61a1c62594472194d2`,
records a17:07:46Z one-shot observation: unit
`ara-whole-history59-candidate04-01.service` not-found/inactive/dead, MainPID0,
empty ControlGroup and timestamps. Journal access was denied; service.log is
empty. Missing-unit Result=success/ExecMainStatus=0 do not verify historical
service exit. This review does not upgrade that evidence.

Independent one-shot `/proc` inspection covered1155 processes without
permission errors: no matching unit owner, worker/output argument, private ELF
or trace argument. No matching cgroup directory remains. No active simulation
was polled, stopped or relaunched.

## Remaining Scope

These are59 independently fresh two-call sequences. Together with the accepted
op partitions they supply the missing local original-adjacency coverage, but
do not establish one continuous1134-call execution, arbitrary longer-history
state propagation, original Linux execution or OS/timing behavior. No claim of
unconditional original-program or historical root-cause closure is made.
