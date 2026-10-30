# Current Attention architectural-retirement attribution

## Question and distinguishing evidence

The accepted current-source complete-call pair is correct but grouped PV is
0.9675% slower. Both schedules already decode V once/token and have identical
QBS busy work. The hypothesis to investigate is that scalar normalization,
coefficient/validation work or the ordinary RVV update schedule limits the
complete call, rather than the native QK compute interval alone.

Collect the current ELF's retired PCs, instruction bits, order, cycle and
destination data. These distinguish how much work retires in the scalar expf,
scale/MAD, value-decode and native-submission functions, and which exact PCs
follow large retirement gaps. They do not on their own establish causal
execution-unit stalls. Compare both schedules, retaining unclassified inlined
orchestration instead of inventing a precise softmax/gather split.

## No new program or hardware

Reuse `verification/out/grouped-pv-fresh-build-20261027-01` exactly, with its
accepted ELF SHA and all seventeen current-source objects. Preserve all four
ABBA calls, full real H6/D128/T128 inputs, numerical/guard/CSR/native-work checks,
and the canonical VCS image. Add only `+COMMIT_TRACE=...` to the simulation
command. The monitor is already compiled into that image. No RTL, compiler
flags, shapes, mathematical operations or tolerances are changed.

The earlier actual run took about an hour, rather than a complete-model RTL
simulation. This run has a three-hour bound. Trace I/O may affect wall time;
do not convert it into a processor performance claim. Do not poll repeatedly.

## Accounting contract

- Both actual linked cycle-CSR sites must match the reviewed build receipt.
  Every trial has exactly one start/end pair, for eight CSR retirements total.
- Retired destination values must reproduce that run's own printed cycle
  delta. Do not transplant the earlier run's cycle measurements.
- Retire order is contiguous from zero; cycle ordering and dual-port order
  must hold. All measured instructions match executable ELF bytes. Traps,
  unknown fields, missing rows, extra/missing CSR boundaries and wrong command
  sequence reject the report.
- Each window must retire exactly four alternating M4/M2 QBS command pairs.
  Backend allocations/completions are separately checked, not counted as
  architectural instructions. Full vector and scalar logs are retained.
- Instruction, function, mnemonic and phase counts partition the measured
  retirements excluding both boundary instructions. Inlined mixed runtime/main
  work remains unclassified. Named helpers are PC contexts, not caller stages.
- Interarrival interval `[previous retire cycle, current retire cycle)` is
  assigned to the NEXT PC. Same-cycle retirements contribute zero gap. The
  final end-CSR gap is separate. These intervals sum to the monitor's retirement
  span, which need not equal the application CSR delta.
- Do not call those intervals function execution time, exclusive stalls or
  functional-unit utilization. Independent protocol and full output checks
  remain prerequisites for accepting the trace.

## Commands

```sh
python3 -B -m unittest discover \
  -s verification/akv/quantized_kv/grouped_pv/attribution -p test_analyze.py -v
python3 verification/akv/quantized_kv/grouped_pv/attribution/run.py \
  --build verification/out/grouped-pv-fresh-build-20261027-01 \
  --output verification/out/NEW_PREFLIGHT
```

After review, add `--execute-reviewed`, use another fresh independent output
directory and give the worker a direct-owned systemd service. Final output
contains the strict call checks, `attribution.json`, source/image identity and
raw evidence hashes. A launched service is not a completed attribution result.

Five new analyzer tests pass, using the existing ELF/CSV fixtures: exact
partitioning, partial/reordered traces, changed instructions/traps/timers,
wrong native command order and wrong ABBA order. These are tool tests, not
the actual hardware attribution evidence.
