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

## Linux counter admission

The first Qwen3 probe run (`graph-cycles-model-20261029-02`) failed on the
first ON timestamp: Linux rejected user `rdcycle` with cause 2. The OFF child
had completed. This is a failed instrumentation run, not a model equivalence
PASS or an RTL arithmetic failure.

The pinned Linux 6.19.6 SBI PMU driver defaults to `perf_user_access=1` and
initializes user counter access to time only. Its supported legacy value 2
allows cycle/time/instret reads, but the driver also stops counters at startup
until perf starts an event. Accordingly there are two separate requirements:

1. Boot this isolated guest with `sysctl.kernel.perf_user_access=2`.
2. Open a pinned `PERF_COUNT_HW_CPU_CYCLES` event on CPU 0 and retain its fd
   throughout the test. This privileged, single-hart experiment includes kernel
   time and is not a production-runtime permission policy.

`counter_preflight.py` uses the same QEMU, firmware and kernel, without a model
disk. The original preflight found that the permission switch alone produced
identical counter values. Its FAIL result is retained. The successor preflight
`verification/out/graph-cycles-counter-preflight-20261029-02` passes both checks:
default policy rejects the child read with SIGILL; explicit permission plus
the perf event allows two strictly increasing reads. Inputs and logs are hashed.

`run_model.py --counter-preflight <that-directory> --output <fresh-directory>`
requires this evidence and matching guest inputs. It starts the same event in
the parent and checks that `rdcycle` advances **before loading the model**.
Both OFF and ON children use the same counter policy and event. The probe
itself still uses unmodified `rdcycle`; no timer fallback or QEMU patch is used.
These QEMU values validate probe execution/accounting only. They must not be
reported as RTL cycles, hardware speedup, or model-level cycle attribution.

Ordinary Linux deployments need their own PMU access and scheduling assessment;
raw cycle reads are not automatically a portable, per-thread execution metric.
The complete-model ON/OFF result and a paired RTL overhead test remain separate
acceptance gates.
