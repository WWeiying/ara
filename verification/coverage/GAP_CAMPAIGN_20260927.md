# 2026-09-27 Coverage Gap Campaign

## Scope

Frozen RTL and the existing VCS instrumented image are reused. No Verilator,
URG, Linux boot, RTL repair, or repeated failed-case retry is scheduled.
Ordinary functional failures are retained while independent tests continue.
Infrastructure errors or image/source drift stop the affected campaign.

Baseline: 298 outcomes, 297 passing cases and one incomplete `vlseg` timeout.
DUT coverage from the expanded DVE report: line 74.10%, branch 73.49%,
condition 72.71%, toggle 56.47%, FSM 42.65%. The testbench-inclusive values
are different; do not compare them to DUT-only percentages.

## Scheduled Work

| Wave | New ELFs | Target |
| --- | ---: | --- |
| gap-01 | 59 | Conversion, widening MAC, reductions, masked/indexed memory, register moves, vector configuration and six short system tests |
| gap-02 | 4 | New operand-extension/reduction matrix, split by SEW; 32/40/48/56 combinations, 176 total |
| gap-02 | 8 | Existing independent integer oracle for FP16-to-I8/U8, 464 cases split into disjoint modulo-8 shards |
| gap-02 | 14 | Eight additional weight profiles, context fill/reuse/release, prebuilt descriptors and AKV portability/D256 reuse |

Total: 85 new ELFs, up to 383 cumulative outcomes. Existing outcomes and
VDBs are reused, not simulated again. A case count is not an instruction
count or a functional coverage percentage. The new tests are compiled and
fit-checked before scheduling; this does not constitute a functional PASS.

The first wave selects `linux_state_prereq`, `linux_vector_context`,
`linux_mmu_relocate`, `sv39_state_prereq`, `trap_state_prereq` and
`stvec_readback`. These are short self-checking programs, not Linux boot.
They cannot prove all supervisor, interrupt or PMP behavior. In particular,
the current SoC's zero PMP-entry configuration is not a PMP verification target.

Selection manifests:

- `gap_rvv_system_20260927.json`: first wave and explicit exclusions.
- `gap_specialized_20260927.json`: second wave.
- `gap_qbs_akv_20260927.json`: application shapes, captured-data identity and
  oracle limitations; its optional larger M8 workload is not scheduled.

## Execution And Evidence

Each wave uses eight workers, isolated ELF copies, logs, traces and VDBs.
Per-case simulation timeout remains 300 seconds or the shorter catalog limit.
No timeout is increased to force a case through. DVE report generation is
separate from simulation and retains its existing 600-second bound.

The second systemd service waits for normal completion of the first wave,
then freezes its inputs, runs the second wave and generates cumulative reports.
The wait is bounded at two hours and stops on predecessor infrastructure failure.
There are never sixteen simulation workers from these two waves at once.

The unchanged directed-case oracle is program selfcheck plus independent trace
audit, not full instruction-by-instruction Spike equivalence. The previous
random results retain their original Spike/scalar/vector evidence. A valid
VDB alone does not establish correctness. Only passing audited cases enter
`passed-only/`; complete failed-case databases may enter the separately
labelled `exploration/` report, never the verified set.

QBS captured golden data are independent of QBS RTL. However, the inherited
numerical comparator does not explicitly reject NaN, so this campaign does
not establish comprehensive exceptional-floating-point correctness. AKV D256
is software grouping of D128 descriptors; optional panel4 support must be
proved from the exercised path, not merely the final PASS message.

## Progress

From the verification worktree:

```sh
./vstatus status vcs-coverage-gap
./vstatus status vcs-coverage-gap-specialized
systemctl --user status ara-vcs-dve-gap-20260927-02.service --no-pager
```

The second entry has no result before its predecessor completes; its live
service is waiting, not executing additional simulators. The service journal
states this explicitly.

Results:

```text
verification/out/vcs-dve-gap-20260927-01/
verification/out/vcs-dve-gap-20260927-02/
```

Each completed wave publishes `checkpoint.json`, per-case `outcomes/`,
`passed-only/summary.csv` and `exploration/summary.csv`. A partial report or
missing summary must not be reported as completed coverage.

## Next Decision

After completion, compare the same hierarchy and denominator against the
baseline. Use new module-level hits to select the next stimuli. Do not promise
a particular percentage increase beforehand. Keep inaccessible configurations,
unexercised legal behavior and debug-only logic separate before considering
any exclusions. Functional failures remain for a separate authorized repair.
