# Software call overhead after the current QBS/AKV optimizations

## Scope and decision

This is a static audit, not a new performance result. The two retirement SoC
workers retain their sealed sources and unchanged ELF inputs. No runtime or
RTL change is made by this audit.

The next optimization decision must include the GGML call boundary. Current
projection and Attention slice timings do not establish full-model speedup or
the cost of all C++ dispatch, allocation, graph traversal and intervening ops.
Do not remove correctness checks to reduce an unmeasured overhead.

## Attention workspace

In llama.cpp `ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp`, `run_prefill`
allocates `workspace_bytes + 63` bytes and releases them on each invocation.
The pointer is aligned to 64 bytes. Decode instead uses an uninitialized,
64-byte-aligned 16 KiB stack array; it has no corresponding heap allocation.
Thus a heap-reuse experiment would target Prefill only, not Decode.

A potential successor is worker-owned bounded scratch, or the existing GGML
workspace if its lifetime and alignment can be established. Before changing it:

- Measure complete operator cycles and allocation count separately from native
  execution cycles, with warm and cold calls distinguished.
- Verify thread ownership, reentrancy, capacity, alignment and cleanup.
- Preserve allocation-failure fallback before any output modification.
- Check CSR admission at the public boundary; moving storage initialization
  before the guard can itself execute vector instructions.

No allocation cost or expected speedup has been measured in this audit.

## Prepared activation cache

`q8_K-prepared-reuse.h` admits single-worker, graph-epoch-scoped reuse for
eligible matrix consumers. `m4-reuse-policy.h` scans at most 128 neighboring
nodes per direction. This is a profitability filter, not cache validity proof.
`q8_K-prepared-cache.h` owns snapshots and validates numerical controls,
producer identity and exact input bytes before reusing quantized output.
Graph pointer or source pointer equality alone cannot replace that comparison.

For four rows and K=1536, input size is `1536 * 16 = 24576` bytes and packed
output size is `(1536 / 256) * 4 * 292 = 7008` bytes. A matching cache entry
therefore requires comparing 24576 input bytes against its snapshot and copying
7008 output bytes. This is not a measured bus-traffic count: comparisons read
two buffers, misses may terminate early, multiple entries may be examined,
and caches affect external traffic. The existing
`comparison_bytes_requested` counter is explicitly a requested-length counter.

Faster quantization changes the reuse break-even point. Compare cache OFF/ON
with the SAME selected quantizer, graph and tensor values; report complete
operator cycles, real producer invocations, cache queries/hits/misses, requested
comparison bytes and copied payload bytes. Do not conflate prepared-buffer
consumers with actual quantization executions. Do not remove snapshot checking
unless the runtime supplies a separately verified immutable lifetime contract.

## Source identity

Inspected in `/home/wangwy/llama/llama.cpp` (external working tree, not a claim
that its changes are committed):

| File under `ggml/src/ggml-cpu/arch/riscv/` | SHA256 |
| --- | --- |
| `quant-kv.cpp` | `d307c171e6a2e6da9870ad78df55863a95562e5eab07d1bbd46c4fffed082c2f` |
| `q8_K-prepared-reuse.h` | `824dba041d07eb85b862c813e1f1ace32a6794c61d5b006f761335d94e1d725a` |
| `q8_K-prepared-cache.h` | `e5d9d46e67cec488bc3ac4a6826bf36c990488a4833c037f3b02e3c7f8a2b186` |
| `m4-reuse-policy.h` | `359ce82df755895c7a69845e0a92437088d8b5f6222f540bf15ca9a856edb0c6` |

First accept or reject the current retirement RTL using its matched SoC pair
and ordinary RVV regression. Then measure these call-layer candidates with a
fixed hardware image; changing both layers together would obscure attribution.

## Graph-level instrumentation constraint

Further inspection of `ggml/src/ggml-backend.cpp:1730` rules out using the
standard evaluation callback as a transparent per-operator timer. With a
callback installed, the scheduler walks nodes, constructs `ggml_graph_view`
subgraphs and calls `ggml_backend_synchronize` before each requested result.
Requesting every node therefore changes graph boundaries and synchronization.

This matters for the current optimization: `m4-reuse-policy.h` searches neighbors
in the supplied graph, while `ggml-cpu.c` assigns a graph epoch to each graph
execution and calls `ggml_riscv_qbs_end_graph` at its end. Single-node graph
views can remove reuse opportunities and change fusion eligibility. Their
timings must not be presented as the cost of the normal optimized graph.

The suitable measurement point is the existing CPU execution loop around
`ggml_cpu_try_fuse_ops` and, for unfused nodes, `ggml_compute_forward`.
Measure fused groups as groups; do not assign the same cycles to every member.
Preserve graph epochs, task selection and all existing barriers. Initially
support single-worker measurements only, since summing worker-local elapsed
cycles does not give multithreaded wall latency.

Instrumentation requirements before adding this probe:

- Compile out by default, including buffer and clock-read overhead.
- Buffer records outside the timed region; no per-node printing, digest or
  tensor dumping during the timed graph.
- Keep allocation, graph scheduling and end-graph cleanup outside node records
  but include them in a separate complete-call measurement.
- Record graph epoch, node/group indices, op, shape, elapsed cycles and clock
  source. QEMU `rdcycle` cannot establish RTL execution performance.
- Compare instrumentation OFF/ON outputs, CSR, command counts, graph epochs,
  fusion decisions and reuse counts before using its cycle attribution.
- Keep normal tracing/digest paths off for performance runs and collect their
  correctness evidence separately; never silently change the execution graph.

This is an implementation constraint derived from source, not a new timer or
completed performance measurement. The accepted software paths remain unchanged.
