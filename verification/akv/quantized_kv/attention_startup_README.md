# Quantized Attention Measurement Entry Initialization

## Failure Evidence And Root Cause

The Q8_0 and Q4_0 complete-Attention runs in
`verification/out/akv-quantkv-attention-{q8,q4}-20261024-02` were interrupted,
not accepted. Their console logs both reached `trial=0 shared=0`, then reported
`insn=42802057` with `exc=1`: cycle 12,342 for Q8_0 and 12,347 for Q4_0.
Neither produced a result record. The disassemblies locate that instruction at
`0x800005ba`, the pre-timer `vmv.x.s zero,v8` drain. A live simulator PID and CPU
consumption were therefore not evidence that useful Attention work continued.

`ara_dispatcher.sv` resets architectural vtype with `vill=1`. QBS capability
queries do not establish an RVV configuration. In the original measurement
entry, no `vset*` precedes the first drain. The dispatcher therefore correctly
rejects the drain: the test helper, not QBS arithmetic, lacks initialization.
The bare-metal exception path does not produce the required completion record.

This is distinct from the earlier test-helper dead-vector-read/printf X spill:
discarding a vector read into x0 avoids that spill, but does not make an RVV
instruction legal while `vill` is set.

## Minimal Correction And Scope

`attention_initialized_main.c` includes the original `attention_main.c` under
a renamed main. Its only extra action is:

```asm
vsetivli zero,1,e32,m1,ta,ma
```

This runs once before entering the original body, outside all measurement
intervals. It establishes a legal vtype and VL=1 for the initial drain. Each
production primitive still configures its own VL normally. No dataset, loop,
head count, token count, QBS descriptor, FP contraction policy, tolerance, guard,
checker or RTL changes. Both baseline and candidate receive the same entry
initialization. The whole experiment must be rerun; interrupted old timings
cannot be promoted into new results.

## Discriminating Probe And Restart Gate

The bounded `attention_startup_probe.c` reads reset vtype, executes the same
QBS capability query, initializes vtype, executes the same drain, then checks:

- Before initialization: vtype is `0x8000000000000000` (`vill=1`).
- After initialization: vtype is `0xd0`, VL=1.
- The drain completes, FCSR=0, VCSR=5 and the program terminates successfully.

The short probe additionally clears v8 with `vmv.v.i` after initialization so
the full-program UVM monitor observes an actual vector destination/VID, rather
than reporting its intentional no-vector-work failure. This probe-only write
is not added to the complete Attention benchmark. The first probe's program
completed with the expected CSR values but failed that monitor's no-VID rule;
its raw log is retained and is not labeled PASS.

`run_attention_startup.py` also pins the two archived failing logs, original
build inputs, accepted simulator, ELF and source identities; it requires
independent CVXIF/backend event agreement and matching source identities after
execution. This CSR/vector-only probe has no VLSU memory instruction, so it does
not require AXI read/write traffic. Those requirements remain mandatory for the
complete Attention runs. An intermediate probe with event tracing omitted was
rejected by the independent checker; its record is not accepted retrospectively.
This proves only the measurement-entry correction, not Attention numerical
correctness or performance.

Builds use `build_attention_initialized.py`; `--startup-probe` generates a
separate probe-only build type that the complete-Attention worker cannot admit.
The complete successor builds are:

- `verification/out/akv-quantkv-attention-q8-build-20261024-03`
- `verification/out/akv-quantkv-attention-q4-build-20261024-03`

Restart the two full experiments only after the short probe passes. Retain the
original independent QK prerequisite, raw-output numerical checker, backend/AXI
checker and three-hour execution bound. Do not interpret a restart as a PASS.

## Accepted Startup Evidence

The startup-only acceptance is
`verification/out/akv-quantkv-attention-startup-20261024-05/result.json`:
`STARTUP_PROBE_PASS`, simulator exit zero, initial vill=1, initialized vtype=d0,
VL=1, FCSR=0 and VCSR=5. Independent protocol checking passed with one backend
allocation and completion, no aborts and no reported issues. Source/image checks
also passed after execution. The probe simulation took about eleven CPU seconds;
manifest and identity checks are outside that simulation time.

Receipt: `verification/akv/results/quantized-attention-startup-20261024.json`.
The fresh complete runs are
`verification/out/akv-quantkv-attention-{q8,q4}-20261024-03`; their numerical and
performance acceptance is separate and still pending when this entry was made.
