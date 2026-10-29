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
