# Shared integer multiplier benefit measurement

## Completed runs

| Output suffix | Baseline | Shared | Interpretation |
|---|---|---|---|
| `shared_mul_ppa_20261101_02` | Completed, 32416.271510 um2 | 3600-second timeout | No valid final comparison |
| `shared_mul_ppa_bw_20261102_01` | 32416.271510 um2 | 29970.191922 um2 | 7.54584% cell-area reduction; both clk_i setup groups have no violating paths |
| `shared_mul_ppa_dadda_20261102_01` | 32416.271510 um2 | 27676.991839 um2 | 14.62006% cell-area reduction; shared clk_i setup slack +0.0000064373 ns |
| `shared_mul_ppa_booth_20261102_01` | 32416.271510 um2 | 20838.383837 um2 | Selected balanced Booth+Dadda; 35.71628% reduction |
| `shared_mul_ppa_opt123_20261102_02` | 32416.271510 um2 | 24587.303817 um2 | Not selected; 24.15135% reduction |
| `shared_mul_ppa_earlyprop_20261103_01` | 32416.271510 um2 | 20955.143845 um2 | Not selected; 35.35609% reduction |
| `shared_mul_ppa_arithcsa_20261103_01` | 32416.271510 um2 | 20703.983842 um2 | Slightly smaller, but worse COMBO slack; not selected |

The BW run took approximately 24 minutes for baseline and 56 minutes for shared.
Shared still has one COMBO setup violation (-0.20 ns) and 89 hold violations
(worst -0.08 ns); this is not complete timing signoff. Area accounting now reads
`Total cell area` from the mapped area report. An empty, nonfinite or nonpositive
area prevents a successful automated comparison.

Dadda functional acceptance completed in `shared_mul_dadda_20261102_02`.
Product and 24-configuration checks passed on bounded replays of the original
images after their initial 300-second timeouts. The stream test also passed.
The `_01` compile was stopped for constant-index warnings and excessive
zero-node elaboration, not an RTL mismatch. Old evidence is preserved.
Dadda DC took 24m22s for baseline and 50m48s for shared. Shared still has one
COMBO setup violation (-0.15 ns) and 90 hold violations (worst -0.08 ns).
Positive clk_i setup slack is not complete timing signoff.

## Selected Booth version

`shared_mul_booth_20261102_01` passed 425280 product checks, all 24 configurations
(196296 cycle checks and 84464 retired arithmetic checks), and the actual-bank
stream test (9640 accepted, 9639 retired, one reset-flushed). Each SEW passed its
256-transaction II=1 stream. The three compile logs contain no warnings or errors.
Three independent Python arithmetic tests and four collector tests also passed.

Frozen baseline/shared DC comparisons completed in
`shared_mul_ppa_booth_20261102_01`. The selected shared design has no clk_i
setup violations, but almost zero slack, one COMBO setup violation (-0.15 ns),
94 hold violations (worst -0.07 ns), and an infeasible-path warning. This is
not physical signoff. Full-SoC functional/application-cycle acceptance has now
passed; see `SHARED_MUL_SOC_ACCEPTANCE.md`. The implementation remains opt-in,
and FPGA acceptance has not been performed.

Compact retained results are in `evidence/shared_mul_selected_20261103/`.
`ppa.json` is the original selected-run comparison; `soc_audit.json` is the
independent final raw-log audit; `soc_report.json` includes application cycles,
activity and the disclosed debug-option change used to accelerate simulation.
Full source inventories and original binary/log references remain in the
verification output directories; the compact files are not substitutes for
those original inputs when rechecking provenance.

```sh
D=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_mul_dadda_20261102_02
cat "$D/acceptance.status"
tail -n 20 "$D/acceptance.log"
```

## Original experiment details

Output directory:

```text
/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_mul_ppa_20261101_02
```

Two independent, source-frozen DC workers run in `synopsys_workspace`.
The host systemd user services directly own their workers. A separate frozen
collector waits for both workers to finish; it does not rerun synthesis.

Services:

- `shared-mul-ppa-baseline-20261101224332.service`
- `shared-mul-ppa-shared-20261101224333.service`
- `shared-mul-ppa-collect-final-20261101-02.service`

Each DC worker has a one-hour execution bound and independent reports/DDCs.
This run does not write to the global synthesis reports or FPGA sources.

## Comparison contract

Both variants use the same frozen sources and the actual multiplier-bank
instance connections extracted from VMFPU. The only difference is the
`ARA_SHARED_SIMD_MUL` compilation define. The baseline is the current legacy
bank, not a separately optimized or historical multiplier.

Both include identical registered ingress and result boundaries and the full
integer bank: product generation, sign correction, pipeline, accumulate,
subtract, rounding, saturation, operand isolation and result selection.
The extracted wrapper replaces the generic input isolation instances with
equivalent conditional assignments. It excludes the surrounding VMFPU issue
queues, instruction sequencing, complete clock control and result queues.

Constraints match the existing local DC flow:

- TSMC28 BWP12T, typical standard-cell library, same tool/container.
- 1.0 ns period; setup uncertainty 0.15 ns, hold uncertainty 0.075 ns.
- Identical input/output delays, drive and output load.
- Identical compile options and clock-gating style, two CPU cores per worker.
- Main timing result is the `clk_i` path group; input/output paths are grouped
  separately. Inspect `clk_i_max.tim`, not only the global worst path.

Results are local mapped cell area and pre-layout timing, not routed timing,
whole-chip area, application speedup or power. A sustained II=1 result does
not prove equal application cycles or equal clock frequency.

## Functional checks

`functional/baseline/run.log` and `functional/shared/run.log` each report:

```text
PPA wrapper PASS transactions=2048
```

They check deterministic operation/SEW/rounding-mode cycling with random data
against combinational legacy arithmetic. These checks validate the measurement
wrapper; they supplement rather than replace the broader existing arithmetic,
streaming, reset and backpressure regressions.

The first preparation run (`..._01`) was terminated because its measurement
wrapper used the next producer's SEW instead of the stored transaction's
ownership for ingress ready. Its files remain preserved and are not accepted
as final comparison evidence. The `_02` wrapper is frozen and passed VCS in
both modes before any comparison is accepted.

## Status and results

```sh
D=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_mul_ppa_20261101_02
cat "$D/baseline/status.json" "$D/shared/status.json"
tail -f "$D/shared/dc.log"
cat "$D/comparison.csv"
```

`comparison.csv` and `comparison.json` appear only after both workers pass.
The collector rejects modified inputs, mismatched source/constraint manifests,
failed workers and incomplete reports. Its unit tests cover area calculation,
source drift, incomplete-run rejection and invalid area values (4/4 passed).

Area reduction is `100 * (1 - shared_area / baseline_area)`; negative means
the shared implementation is larger. Timing improvement is shared slack minus
baseline slack; positive means improvement under identical constraints.
An area reduction is not sufficient acceptance if timing regresses materially.

Reproduce in a fresh output directory:

```sh
python3 verification/timing/run_shared_mul_ppa.py /absolute/path/to/new-output
python3 verification/timing/collect_shared_mul_ppa.py /absolute/path/to/new-output --wait
```

The launch helper snapshots inputs and starts the two background services.
Run the optional collector under an independently owned service for detached
operation, as done for the current run.
