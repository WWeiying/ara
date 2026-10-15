# Candidate03 Representative Regression

**16/16 PASS; all16 complete cycle-bearing commit traces byte-identical to
candidate02.** Reused the existing candidate03 image, with no build, RTL edit,
software change, oracle change or commit. This supplements the accepted
[focused11 evidence](CANDIDATE03_REVIEW.md), not a rerun of all38 arithmetic
programs or the original Linux families.

## Exact Inputs And Oracle

The ten ELF inputs are copied from actual candidate02 `campaign/smokes/tests/`.
The six singles are copied from actual candidate02
`integration/memory_regression_plan02/replay/tests/`. Each copy matches the
original programs manifest, baseline inputs.json and baseline ELF SHA256.
All original pass markers, zero process returncode and firmware tohost=0 were
required, with no SKIP exemption. `slide1up_prestart` remains a directed
supplement; the other five singles are the existing selected source ports.

The runner uses the sealed candidate03 verification framework with skip-build,
seed1, jobs2 and 180 seconds per program. Candidate02 observed times were
14.30..85.23 seconds, totaling708.88 seconds; the chosen per-case bound exceeds
twice each observation. The service outer bound1800 exceeds the1440-second
worst-case serial-work/jobs budget plus validation margin. No retries or
timeout changes were made.

## Measured Results

| Exact program | M3 wall seconds | CSV event rows | Last recorded cycle | Complete M2/M3 CSV |
| --- | ---: | ---: | ---: | --- |
| rvv_vadd | 98.31 | 40797 | 65438 | Identical |
| rvv_vslideup | 87.98 | 33635 | 56008 | Identical |
| rvv_vslidedown | 72.16 | 26447 | 41490 | Identical |
| rvv_vrgather | 49.39 | 17283 | 28256 | Identical |
| rvv_vmseq | 107.15 | 43836 | 65658 | Identical |
| rvv_vfredosum | 84.50 | 32611 | 51740 | Identical |
| rvv_vfwredosum | 56.03 | 21708 | 34438 | Identical |
| qbs_control_smoke | 15.45 | 1259 | 4383 | Identical |
| akv_context_smoke | 40.78 | 14990 | 25397 | Identical |
| qbs_akv_handoff_smoke | 24.71 | 4685 | 11318 | Identical |
| maskslide | 39.96 | 11578 | 19497 | Identical |
| restart_compare | 66.39 | 18975 | 30318 | Identical |
| reduction_fflags | 24.60 | 5381 | 9435 | Identical |
| m8widen | 39.76 | 12408 | 21158 | Identical |
| wholemove | 63.76 | 23161 | 33222 | Identical |
| slide1up_prestart | 15.76 | 1596 | 3046 | Identical |

The16 CSVs total310350 events and34344881 bytes. Equality includes headers,
all events, instruction/data fields and every recorded cycle, not a normalized
target-only comparison. Walltime differences are host scheduling, not measured
RTL cycle regressions. `reduction_fflags` also retains its original flags_seen=16
oracle. All numerical/error-count markers are pinned in the plan.

Service `ara-fp-moves-controls16-01.service` terminated normally:
MainPID=0, inactive/dead, Result=success, ExecMainStatus=0. Run and final
validation took470.72 host seconds. The launch and all16 admission checks
reserved both own slots plus any unoccupied NF7 two/alias one slots; maximum
admitted total23/24, minimum MemAvailable183342026752 bytes. Other jobs were not
modified or interrupted. NF7/alias continue to use **candidate02**, not M3.

## Pins And Reproduction

The runner and a separate post-terminal check rehashed all1305 plan pins with
zero mismatches, covering both539-file snapshots, images, helpers, source
manifests, baseline traces/oracles and exact ELF inputs. Runtime inputs.json
identifies candidate03 for all16 runs. Final summary, full console oracles and
raw bytes were rechecked independently of the recorded PASS booleans.

- [Plan and original markers](candidate03_controls16_01/plan.json)
- [Terminal results and full trace hashes](candidate03_controls16_01/complete.json)
- [Actual runner summary](candidate03_controls16_01/replay/summary.json)
- [Launch resources](candidate03_controls16_01/resources.json), per-case `admission/`
- [Minimal replay runner](replay_controls16.py)

Plan SHA256: `da9fbe0b4e773762516456694c1a8da8bf1e7c8d2322dae9af675e1a8205f5ea`.
Terminal JSON SHA256: `ba5bfde04d3e0f47b680e06edbd9eb42adbbb8806cbce5b3eb2b41c3e6f33304`.
M3 image ledger SHA256: `e2c32c314ca85042e49517476d36c93d0d1f8a9c8eae75d86602cef1de476cb6`.
M3 simv SHA256: `d7c37b993c8af577f00578dacff3cb9af4ea250fae95e1bfece7df33213bbd66`.

For a separately authorized replay, choose a fresh owned output directory and
invoke `replay_controls16.py prepare --out <fresh-directory>`, then `run` with
the same directory. Neither mode builds an image or changes inputs. The retained
01 output and plan are not overwritten.
