# Old-image floating-point operand LZC coverage

This batch extends the 669-PASS gap76 aggregate using the identical frozen
VCS image. It changes stimulus and campaign plumbing only, not RTL.
Known RTL failures remain excluded and are not repaired in this campaign.

The source-indexed 654-test inventory contains unhit condition combinations
in the LZC trees under MFPU operand queues. Gap76's small integer inputs do
not systematically exercise mantissa bit positions. Four new tests target
that gap, rather than repeat ordinary widening with another random seed.

| Test | Data and operation |
| --- | --- |
| vgap77_onehot16 | All 10 FP16 subnormal mantissa one-hot positions; widening multiply by 1 |
| vgap77_onehot32 | All 23 FP32 subnormal mantissa one-hot positions; widening multiply by 1 |
| vgap77_dense16 | Dense low mantissa bits, alternating signs and signed zeros, FP16 |
| vgap77_dense32 | Dense low mantissa bits, alternating signs and signed zeros, FP32 |

Each test uses LMUL 1/2, short/odd/near-full/full VL and zero/sparse/full
masks. Destination tails and masked elements are checked. Widening these
finite source values is exact and multiplication by 1 is exact; fflags
must remain zero. The scalar oracle is independently executed by Spike;
the full vector writeback comparison checks bit patterns including signed
zeros, in addition to the DUT's scalar numerical self-check.

The runner reuses `run_gap76_old_image.py` with explicit cases and baseline.
Up to eight workers are allowed, four are occupied in this batch. Every
case must pass Spike before VCS and full scalar/vector comparison and DUT
checks before coverage admission. Failures are recorded and excluded.
Only compatible PASS VDBs are appended to the previous 669; the report
uses raw, non-waived DVE coverage. No increment is claimed before export.

Output: `verification/out/gap77-old-image-20261006-01`.

Progress commands (from this worktree):

```sh
./vstatus jobs gap77
cat verification/out/gap77-old-image-20261006-01/status.json
```

The current runner writes each final verdict when the worker completes;
per-case `QUEUED` in status.json does not imply an idle process. Use the
service's live child processes and growing trace files to confirm activity.
At initial launch all four Spike preflights passed and all four VCS
processes were live. The batch and DVE export subsequently completed.

## Measured test and target results

All four tests passed complete Spike scalar/vector comparison and DUT
self-checks: FP16 cases each performed 1,820 checks, FP32 cases each
performed 924 checks. No new RTL failure was observed in this batch.
There are 673 compatible PASS inputs after appending these four to 669.
Official DVE export completed with the following raw i_system results:

| Metric | 669 PASS | 673 PASS |
| --- | --- | --- |
| Line | 80.39% | 80.39% |
| Condition | 81.12% | 81.13% |
| Branch | 79.94% | 79.94% |
| FSM | 60.46% | 60.46% |
| Toggle | 62.87% | 62.87% |

These are rounded native DVE percentages from each aggregate's
`combined-dve/summary.csv`, not raw bitmap percentages. The recorded
`status.json` has status and coverage_status both COMPLETE.

The raw system bitmap delta is six condition points, zero line/branch/FSM
points. The six additions belong to CVA6 scalar floating-point input
classifiers used by the oracle calculations. They must not be described
as new vector operand-queue coverage.

The specific LZC hypothesis did not produce new target hits: the
source-indexed inventory identifies 381 historically unhit mixed-metric rows
under MFPU queue LZC trees still unhit before and after this batch.
Evidence is `lzc-target-delta.json`; raw overall additions are in
`raw-bitmap-delta.json`. The snapshot comparison checks identical design,
point shape/checksum and inclusion of the baseline test population.
These are diagnostic raw points, not official DVE denominators.

Do not repeat the same data-pattern tests to inflate the case count.
Before another LZC campaign, inspect native condition truth tables and
reachability: non-power-of-two LZC trees contain constant padded nodes,
and not every uncovered truth-table row is necessarily feasible. No
automatic waiver or claim that all 381 rows are unreachable is made here.

Follow-up clarification: the initial target export included line and
branch metrics as well as conditions. `lzc-condition-delta.json`, using
the explicit condition-only filter, has 321 unhit condition points before
and after this batch. The tool now defaults to a condition-only filter;
its metric-selection regression test prevents mixing these counts again.
The separate LZC diagnostic and the next stimulus hypothesis are described
in `GAP78_OLD_IMAGE.md`.
