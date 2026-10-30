# GGML multirow activation-context acceptance

This sidecar builds the actual external GGML CPU backend without editing its
checkout. It exercises `GGML_OP_MUL_MAT`, production weight repacking and
activation preparation, the QBS runtime planner, and native custom instructions
in the attested QEMU model. It is not a cycle simulator or a new performance
benchmark. The real captured projection pairs remain the performance evidence.

## Matrix

All graphs have 37 output columns. Each graph runs two epochs with the same
activation allocation but different contents; output bytes must change.

| Weight / activation | M | K blocks |
| --- | ---: | --- |
| Q8_0 / Q8_0 | 1 | 1 |
| Q8_0 / Q8_0 | 3 | 17 |
| Q8_0 / Q8_0 | 4 | 28, 32, 33 |
| Q8_0 / Q8_0 | 5 | 1, 17, 28 |
| Q8_0 / Q8_0 | 8 | 17, 28 |
| Q8_0 / Q8_0 | 9 | 17 |
| Q4_K / Q8_K | 4 | 2, 4, 5 |
| Q4_K / Q8_K | 8 | 2, 3 |

Q8_0 blocks contain 32 elements; Q4_K blocks contain 256. The bounds are
chosen to exercise both the 32-block limit and the 4672-byte context budget,
including M4/M8 slabs, padded M5 rows and an M9 tail. Capacity fallback means
native QBS DIRECT execution, not silently skipping the graph or changing its
format. M2/M3 row-major context rejection is additionally covered by the
bare-metal instruction contract.

Six independent guest processes select context off/on for each of:

1. Wide M disabled, one GGML thread.
2. Wide M enabled, one GGML thread.
3. Wide M enabled, three GGML threads.

This produces 16 shapes x 2 epochs x 6 policies = 192 graph executions.
The three-thread runs deliberately use a single QEMU hart to test software
interleaving. They do not establish multicore context ownership, task migration,
or OS save/restore of custom architectural state. Cross-operator reuse is off
to isolate the operation-local multirow policy.

## Independent checks

`test.cpp` constructs finite, exactly quantizable activations so that reference
and production tail quantizers must agree byte-for-byte with a scalar formula.
The scalar decoder reads original row-major weight bytes, not the production
R4 representation. Outputs are compared with a double-precision dot product at
the existing `2e-4 + 2e-5 * abs(expected)` tolerance. Neither the QBS reference
executor nor its dot routine is linked as an oracle. This mapping/lifetime test
does not replace special-value, rounding-boundary or real-model accuracy tests.

The host checker also audits native command work, context capacity/lifetimes,
all expected graph records, and output digests between context-on/off runs at
the same width/thread policy. A numerical PASS without the intended dispatch
is insufficient. Build, runtime, kernel, QEMU and test source identities are
sealed before execution and rechecked before reporting PASS.

## Run

Use a new output directory and the new-capability QEMU build:

```bash
python3 verification/qbs/run_ggml_tile_context.py \
  --output verification/out/qbs-ggml-tile-context-20261023-01 \
  --qemu verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64
```

For background execution, the transient service must directly own that Python
worker. `status.json` distinguishes configure/build/run/PASS/FAIL, records the
active child PID, and points to its log. A successful launch or successful
build is not a completed acceptance result. The runner has a bounded guest
timeout and does not overwrite old directories or rebuild shared QEMU images.
