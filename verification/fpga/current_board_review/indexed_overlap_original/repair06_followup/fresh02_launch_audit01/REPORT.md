# M6 Fresh02 Launch Audit

PASS for launch prerequisites only; no regression48 result is claimed.

- Frozen successor a78191e2..., plan ee0b810e...: all889 pins match, all prior885 preserved.
- Offline replay of the read-only admission validator matches saved admission exactly: three cases and29 evidence hashes.
- All three full50-round cases PASS/rc0, no abort;48405 recorded oracle checks,3200 repairs/retries.
- Recorded service proof is loaded/inactive, MainPID0, Resultsuccess, ExecMainCode1/status0, no residual owner.
- Persistent witness independently binds original PID620452 and InvocationID94f592605b7147d3b5e47923457f3078 to actual exit0.
- Followup MainPID628354 owns child675396 in the same cgroup; sealed regression48 command/plan/image match.

## Ordering

- predecessor_complete: 2026-10-11T21:47:44.636077+00:00 (1791755264.6360774)
- predecessor_actual_exit: 2026-10-11T21:47:44.680327+00:00 (1791755264.680327)
- witness_observed_exit: 2026-10-11T21:49:43.081624+00:00 (1791755383.0816243)
- followup_admission: 2026-10-11T21:50:12.899238+00:00 (1791755412.8992379)
- regression_child_launch: 2026-10-11T21:50:14.764802+00:00 (1791755414.7648017)

Actual exit precedes regression child launch by 150.084475s.

The frozen code rechecks pins/shared validators and full predecessor evidence at lines307-310,
requires real loaded exit0/no owners at311-312, writes admission at319, then invokes Popen at324.
The strict GC refusal remains at137; old prepared01/helper files were not changed.

## Limits

No service/process queries, running regression CSV reads, or simulation launches were made.
Parent observation of four actual M6 original38 simvs is attributed, not re-observed.
This is not an independent fullCSV oracle recomputation or a48-case acceptance.
Machine-readable report.json pins the launch records, witness evidence and audited inputs.
