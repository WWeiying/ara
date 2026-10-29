# Graph-preserving cycle attribution (preparation)

This is not an installed llama.cpp timer. `records.h` is the independently
tested record collector for an opt-in CPU-loop probe. It takes caller-supplied
storage and timestamps and performs no allocation, logging, synchronization,
floating-point operation or RVV operation. It refuses multithreaded collection,
overlapping node groups, backwards timestamps, insufficient capacity and failed
graph completion. Fused followers occupy one record, not duplicate cycles.

The integration must allocate graph-owned storage before measurement, bracket
actual `ggml_cpu_try_fuse_ops`/`ggml_compute_forward` execution without changing
graph views or epochs, then finish after end-graph resource cleanup. Empty and
non-compute nodes are skipped as in the original loop. Print only after the
complete graph interval ends. Store tensor metadata after the node timestamp,
not inside its interval. Attribute fused groups using first/last node indices.

Use compiler-ordered RV64 `rdcycle` reads without inserting new architectural
fences. The resulting interval measures CPU execution between reads, not a
claim that every asynchronous accelerator or store has drained. A separate
application-level completion boundary must establish complete-call latency.
Reject/label unavailable counters; do not substitute QEMU counts as RTL cycles.

Compile-time OFF must remove all timer/storage code. Initially require a single
CPU worker and no graph callbacks, node digest/dumps or per-call trace printing.
The collector's elapsed graph interval includes its record-write overhead;
recorded node intervals exclude it. Do not describe their difference as purely
application overhead. Do not subtract an assumed constant probe cost.

Remaining integration gates: real-source OFF/ON builds; identical graph epochs,
fusion/reuse decisions, outputs, CSR and command counts; bounded representative
RTL paired run. Host record tests prove accounting only, not these gates.

## Isolated integration

`prepare.py` inserts compile-time-guarded probes into a fresh copy of
`ggml-cpu.c`, rejecting ambiguous anchors. It never edits the source tree.
Line directives preserve the original source location when the probe is OFF.
`check_build.py` uses the accepted library's compile recipe to rebuild original,
OFF and ON objects without replacing any library object.

The 20261029 build in `verification/out/graph-cycles-compile-20261029-01`
passed all three compilations. Original/OFF preprocessed text and object bytes
are identical. Source SHA256:
`2d9e4b8e4d38bb6cb64ca54abd4259f68c4aab7222fb2fb7391b973baf0958e3`.
This does not yet establish ON runtime equivalence or timing overhead.

Enable both compile macro `GGML_RISCV_NODE_CYCLES` and environment variable
`GGML_RISCV_NODE_CYCLES=1` in an isolated experiment. Multithreaded graphs,
model observation/dumps or known QBS/AKV trace printing disable collection.
Allocation failure also disables collection and does not alter inference.
Absence of a valid graph record is missing measurement, never zero cycles.

Records include the unmodified no-op trace-function call inside the execution
region when model tracing is disabled. Graph time starts after buffer allocation
and ends after existing end-graph cleanup, before printing/freeing the buffer.
It is not complete `llama_decode` time and excludes graph setup and allocation.
No production file or previously accepted library was modified.
