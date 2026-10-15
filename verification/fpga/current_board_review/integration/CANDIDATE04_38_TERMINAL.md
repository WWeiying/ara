# Candidate04 Selected38 Terminal Audit

The unchanged38-program M4 replay completed at2026-10-11 04:02:49 -07:00.
`ara-candidate04-arithmetic38-03.service` is inactive/dead with Result=success
and ExecMainStatus=0. Its terminal status is `PASS_38_CANDIDATE04`.

Plan SHA256:
`6a4b74d7bea9025771fcfb4e48204b58b5bfc80f40450eeec7e0e4f900cc93b9`.
Image-ledger SHA256:
`e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.

An independent parent read-only check established:

- All1368 pinned files still match their hashes.
- Plan, terminal results, runner summary and completed run contain the same38
  unique ordered program names, each PASS with return0 and no failure reason.
- Each executed private ELF matches the planned hash and its inputs record;
  every inputs record identifies the expected complete frozen M4 simulator.
- All76 console and VCS logs contain the case's required oracle markers,
  successful tohost0 and normal finish, with no raw RVV/board/matrix/extension/
  epoch failure, trap/mismatch, fatal or VCS error markers.

This supplements the runner's strict per-case checks. It is not a fresh
independent row-by-row recomputation of all38 commit traces, nor a claim of
cycle equality across revisions. Earlier representative16 trace comparisons
remain the scoped performance evidence. The38 selected programs are unchanged
from the earlier M2 regression; they are not the full original22-shape
arithmetic matrix or Linux board binaries.

## End-cycle Comparison

Read the last complete CSV event in each matching program from M2
`memory_regression_plan02/replay/tests/` and M4
`candidate04_regression38_03/replay/tests/`. All38 matching files were present.
For36 programs the final event cycle is unchanged. The two differences are:

| Program | M2 final event cycle | M4 final event cycle | Difference |
| --- | ---: | ---: | ---: |
| singles__restart_compare |30318|30319|+1|
| combined__all |111798|111799|+1|

These are whole-test trace end cycles, not kernel-only ROI cycles, and equality
of the last cycle does not establish equality of every intermediate event.
This scoped comparison shows no material whole-test cycle regression across
the selected38; it does not generalize to all masked-memory workloads.

Artifacts: [complete](candidate04_regression38_03/complete.json),
[run](candidate04_regression38_03/replay/run.json),
[summary](candidate04_regression38_03/replay/summary.json).
The four live slots are released. Gather75 terminal acceptance and NF8 initial
admission have subsequently satisfied the remaining scheduling gates.
Arithmetic prefix5 has started; FP plan07's launch stopped before any DUT
simulation because its service query did not handle an already collected
Gather unit. See `../fp_comparison_original/PARENT_LAUNCH07_NOT_STARTED.md`.
That launch-check failure does not change the38-program functional result.
