# Whole1134 Independent Terminal Audit

PASS: exactly20 operation partitions on frozen candidate04/M4, covering1134
original tuples and366 original exclusions. This is partition-only acceptance,
not continuous `whole_all`, original Linux ELF execution, or the future59
history-edge pairs. No DUT, rebuild, RTL change or old terminal overwrite was
performed. Machine-readable evidence is `terminal_audit01.json`; the successor
gate record is `strict_acceptance01.json`.

## Independent Checks

Read-only imports reused the existing replay reference/identity/pin checks,
strict raw-console checker and frozen M4 `ara_verify.trace.validate_trace`.
All20 complete CSVs were parsed again, not accepted from stored PASS labels.
An additional retirement scan checked each original tuple in order, original
input/output pointers, mode and vstart arguments, exact target opcode, actual
pre-target vstart readback and zero post-target vstart. Each call independently
checked all1088 scalar output reads against the original seed/start/width
oracle, including prestart and both surrounding guard regions.

- Exact target count1134; original excluded tuple count366; no duplicate or
  missing `(seed,op,mode,index)` membership. Whole-op00..11 and13..15 each have
  60 cases/15 exclusions; op12 has45/30; op16..18 each48/27; op19 has45/30.
- Total27209016 retired instructions and1233792 independently checked output
  byte reads. All CSVs passed contiguous-retirement, monotonic-cycle and
  CVX/architectural/backend sequencing checks; no retire traps or CVX exceptions.
- Each console.log and work/run.vcs.log passed raw failure/DETAIL/BYTE veto,
  exact original cases/skips/errors=0 markers, BOARD completion, tohost0 and
  `$finish` checks. All20 private ELFs, inputs.json records, simulator commands,
  PRELOAD paths and working directories match the pinned plan and M4 image.
- Runner COMPLETE, exact PASS:20, all rc0/empty reasons, exact summary and
  terminal membership, no firstfailure.json. The legacy terminal has no
  explicit `aborted` field: no-abort evidence is COMPLETE (not INTERRUPTED),
  all20 noncancelled results, raw logs and parent-observed successful exit;
  no synthetic aborted=false assertion is attributed to the old runner.
- All927 original pins rehashed unchanged before and after the full scan.
  Current frozen snapshot, compiled-source manifest, image files and configuration
  identities were revalidated. Original oracle body and complete tuple geometry
  remain unchanged; only the already-reviewed wrapper/partition bounds apply.

Maximum case elapsed2186.147093s, below5400s; launch-to-terminal7423.802352s,
below the original30000s service bound. Summed case elapsed37633.854388s is
parallel-worker time, not campaign wall time.

Plan SHA256: `4026384e0a1bb8f3163c8f4604bfa08a95350b3d12e49f2bbafdbe5696a84269`.
M4 image.json: `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
Old complete.json: `396d775107adaee48285ec6e0cac5b60bfa379e4d3da92afdb5a3180ab09f5b9`.

## Service Attribution and Slot Release

Parent explicitly reported its on-site terminal observation of
`ara-whole1134-candidate04-01.service`: inactive, MainPID0, Result=success,
ExecMainStatus0. These successful-exit facts are parent-observed, not an
independently recovered numeric exit code.

This audit's one trusted-user-bus query instead found the already-collected
unit: rc0, not-found/inactive/dead, MainPID=ControlPID=0, empty ControlGroup.
Default post-GC Result/ExecMainStatus/RuntimeMax values were not treated as
historical execution evidence. The independent all-process/cgroup check at
1791723528.299611 examined1206 processes and found no old-owned process or
unit cgroup. Combined with the accepted raw terminal evidence and parent's
service observation, the old6-slot reservation may be released/replaced for
parent-coordinated Whole59 admission. No Whole59 launch is performed here.

The new acceptance record binds this audit plus every partition's CSV, private
ELF, inputs, command, both raw logs and trace summary, and old plan/complete/
run/summary. Its service attribution remains explicit outside the strict
service-object schema required by the successor gate.
