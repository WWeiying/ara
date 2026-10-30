# Four-row prepared-activation reuse: investigation and design

The accepted vector-byte implementation is installed behind the opt-in
`GGML_RISCV_QBS_M4_CACHE` switch. Normal CMake build and graph gates pass;
the final normal-library model gate also passes. Default behavior remains
unchanged. The experiments below retain their precise scope and do not
represent additional whole-model speedup measurements.

## Measured opportunity

The accepted runtime trace still contains 166 exact-byte duplicate M4/K1536
preparations per recorded model process: 112 in V/K projections and 54 in
FFN-up projections. These produce 1163328 duplicate bytes. The trace producer
compares bytes after its identity/hash checks; pointer equality alone is not
the evidence. These counts describe the recorded Qwen2.5 graph, not all models.

The Q/V/K Prefill captures each contain F32[1536,15]. Their first four rows
are byte-identical, SHA256
`913afc315e1a3da1191ec74fe9faab17bdf25d4c672624a2c65192438cc8beb1`.
The existing cropped test input is those real rows, not synthetic data.
Its prepared M4 Q8_K image is 7008 bytes: six blocks of 1168 bytes.

## Why not simply enable M4 hardware-context reuse

`qbs_activation_context.sv` physically retains 16 Q8_K block equivalents,
4672 bytes. The descriptor decoder and SDK enforce that same capacity.
Extended shape/tag support does not enlarge the SRAM. M4/K1536 needs
7008 bytes and therefore cannot fit. The payload streaming window is a
different resource and is not an implicit persistent copy of the entire K
range. Removing the capacity check would be incorrect.

M4 is not categorically unsupported in hardware: smaller capacity-bounded
tiles can fit. Separately, the current GGML cross-op identity path admits
only one input row. Neither restriction should be removed to pretend that
this measured four-row case already works.

## Software ownership problem

`repack.cpp::forward_mul_mat` quantizes into `params->wdata` and the chunk
execution path reads that same work area. Intermediate operators may reuse
it. A retained pointer is not persistent prepared data, even when the original
activation tensor survives. Any software cache must own its bytes separately.

Two possible admission strategies are:

| Strategy | Advantage | Additional proof burden |
| --- | --- | --- |
| Tensor identity + graph lifetime scan | Avoids rereading input on a hit | Complete alias/write/custom-op handling, epoch and cancellation ownership |
| Owned input snapshot + exact value comparison | No stale-pointer or graph-lifetime assumption | Extra input snapshot, comparison/copy cost and numerical-state replay |

Prefer investigating the second strategy first. A prepared block is a pure
function of its input bits and numerical controls within the admitted domain.
Comparing all input bytes against an owned copy also handles reused addresses,
in-place writes and different graphs without trusting address identity. Do
not substitute a digest-only hit test. An optional pointer/shape check can
reject quickly but cannot establish a hit.

At K1536, one four-row entry would own 24576 input bytes plus 7008 prepared
bytes, excluding metadata. This is software RAM, not new RTL storage. A
bounded, lazily allocated, per-thread cache could retain several groups.
Its size/admission policy must be tested for larger Prefill batches to avoid
sequential-scan thrashing; a single last-result slot is not sufficient for
general multi-group inputs. The installed opt-in wrapper now uses the
eight-entry/1 MiB bounds below, with prefix admission for longer inputs.

## Numerical-state contract

The existing `q8_K-m4.h` vector producer admits RNE and its checked finite
domain; other modes use the existing generic fallback. Its vector path uses
truncating narrowing, not saturating clipping, and does not depend on VXRM.
The investigated replay path must preserve incoming VCSR and require
`vstart=0`. Non-RNE calls remain uncached.

Skipping computation can otherwise lose floating-point exception flags.
Capturing `after & ~before` is insufficient when an exception bit was already
set before the first quantization. Instead, within an admitted computation:

1. Save incoming sticky flags, retain FRM, and clear only FFLAGS.
2. Run the normal producer and capture independently raised flags.
3. Restore incoming flags OR raised flags.
4. On a valid byte-cache hit, copy prepared bytes and OR the recorded raised
   flags into the caller's current flags. Do not replace current flags.

This relies on ordinary nontrapping RISC-V floating-point sticky-flag
semantics and on the producer not explicitly clearing flags itself. The
current producer satisfies that static condition. It does not promise to
reproduce caller-clobbered vector-register contents or VL/VTYPE; those are
not the C library's preserved output state. The supported ABI still requires
zero restart state.

## Completed state-replay probe

`verification/out/m4-state-replay-20261027-01/result.json` is PASS. The probe
uses the actual shared M4 producer in a separate translation unit, real
captured input, the previously checked prepared-byte image, and the normal
rebuilt libraries. QEMU has the QBS extension disabled, so no custom hardware
instruction can accidentally replace the tested standard-RVV preparation.

All 262 checks passed:

- Capture from incoming FFLAGS=17 and VCSR=5, preserving caller state while
  independently observing the producer's NX flag (1).
- 32 incoming flag masks times eight VCSR values: exact prepared bytes,
  buffer guards and FCSR/VCSR agree with actual recomputation.
- Four non-RNE controls are rejected without output/state changes.
- Nonzero restart state is rejected without being silently consumed.
- Original input bytes remain unchanged.

Log SHA256:
`8c8f10a30c69edf7f6ed42d966b1d294bb69ad8f48e1f722730e8594e961e566`.

This is a byte/CSR replay proof for the real admitted input, not a cache
implementation, exhaustive input-domain proof, graph integration or hardware
speedup measurement.

## Next implementation gates

### Multi-group capacity and admission

An independent exact-input residency replay now reads the full captured
layer-0 Prefill activations, F32[K,15], rather than repeating only the cropped
first four rows. It visits Q, V, K, attention output, FFN gate, FFN up and FFN
down, using their actual binary inputs. The report pins both tensor metadata
and binary data. This is an explicit sequential preparation-order replay,
not a new observed GGML scheduling trace or a quantizer-domain acceptance.
It assumes one worker, the same eligible producer and numerical controls;
byte equality is a potential reuse opportunity, not measured acceleration.

Each operator has three four-row groups plus three single-row tails. For
the six K1536 operators, an entry owns 31584 bytes. The K8960 FFN-down entry
would own 184240 bytes, exceeding this prototype's 128 KiB per-entry limit;
its three groups remain uncached. This is a software policy limit, not an
additional hardware or model support restriction. All 21 single-row tails
remain outside this M4 cache experiment.

| Retained entries | Ordinary LRU potential hits | Prefix-admission potential hits | Peak retained payload |
| ---: | ---: | ---: | ---: |
| 1 | 0 | 3 | 31584 bytes |
| 2 | 0 | 6 | 63168 bytes |
| 3 | 9 | 9 | 94752 bytes |
| 4 | 9 | 9 | 126336 bytes |
| 8 | 9 | 9 | 252672 bytes |

Prefix admission is a proposed caller policy: only the first S groups of
each operator may access the S-entry cache; later groups compute normally
without inserting. It avoids destroying useful entries during a long scan.
In a distinct-input nine-group unit test, an eight-entry ordinary LRU has
zero hits across Q/V/K; prefix admission retains 16 potential hits while
three last-group calls compute normally. This larger-batch example tests
policy behavior with generated bytes, not real model timing or arithmetic.

Both policies retain exact-value hit validation. Prefix admission does not
make pointer identity sufficient and does not skip computation for uncached
groups. It is not yet integrated into production or the active single-group
VCS experiment. Before integration, thread-local group numbering and the
actual GGML iteration order must be tested, as must comparison costs across
several retained entries.

Reproduce with `analyze_capture_residency.py --captures CAPTURE/operators
--output NEW_REPORT.json`. Seven unit tests pass. The real-input report is
`verification/out/m4-residency-20261027-02.json`, SHA256
`33206fc7c79bf23325703954697839e8953d1f9cea800acfd6de10acff88356f`.

### Experimental cache implementation

`verification/qbs/m4_prepared_reuse/value_cache.hpp` now implements the
independent prototype. That verification-only file remains archived; the
installed runtime uses the promoted canonical header. Each entry
owns both snapshots; a hit requires exact input bytes and matching producer,
shape, layout and numerical controls. A conflicting prepared result for the
same key/input invalidates the old entry rather than returning it. Allocation
failure preserves existing entries. Cache instances are worker-local and are
not internally synchronized.

Experimental defaults are eight entries, 1 MiB retained payload and 128 KiB
maximum per entry, with lazy allocation and LRU eviction. Metadata is extra;
replacement can temporarily allocate one additional entry. These defaults are
not a production memory-budget decision. Returned flags are independently
captured producer flags; the caller must OR them into FFLAGS. The byte-cache
class neither reads nor changes architectural CSRs.

The host test passed 8064 checks with Clang undefined-behavior instrumentation
on 2026-10-27. Checks include owned snapshots, equal data at different
addresses, first/middle/last mutations, LRU, duplicate/conflicting insertion,
allocation failure, exact capacity limits, invalid controls, overlapping
buffers, guards and 2000 successive source-address reuse iterations. Run:

```sh
clang++ -std=c++17 -O1 -g -Wall -Wextra -Werror \
  -fsanitize=undefined -fno-sanitize-recover=all -Isoftware/qbs/include \
  verification/qbs/m4_prepared_reuse/cache_test.cpp -o /tmp/m4-cache-test
/tmp/m4-cache-test
```

The host test covers byte-cache management. A separate real-producer check
now covers byte and CSR replay through this implementation:

`verification/out/m4-cache-replay-20261027-01/result.json` is PASS, with 269
checks. It uses the original real M4/K1536 input and prepared-byte oracle,
the actual shared quantizer in a separate translation unit, and the pinned
normal runtime libraries. QEMU runs with `xaraqbs=false`.

- One cold computation and 256 warm calls cover all 32 incoming FFLAGS masks
  and eight VCSR values. Results and guard regions match recomputation.
- Three changes at first/middle/last input elements each cause a miss and a
  real computation, followed by a hit. Restoring original input hits the owned
  original snapshot. Total: four computations, four misses and 260 hits.
- Four non-RNE controls and nonzero vstart are rejected without consuming the
  unsupported state. No production fallback is replaced by this test wrapper.

The test records SHA256
`7b425dd265d18f3270c57c3033253f24050dfce35956ecccba05852daad6ed84`
for its QEMU log and checks inherited source/library pins before and after
execution. Reproduce with:

```sh
python3 verification/qbs/m4_prepared_reuse/run_cache_replay.py \
  --output verification/out/m4-cache-replay-NEW
```

This is functional evidence for the real captured input and its tested
mutations, not exhaustive quantizer-domain testing. Measuring cold misses,
comparisons and copies on RTL, multi-group admission policy and normal-runtime
integration remain subsequent gates. No additional hardware or model speedup
is claimed here.

### Full captured groups and single-row tails

`run_group_replay.py` adds a separate standalone functional check using the
complete 15-token Q, V, K, FFN-gate and FFN-up input captures. Each input has
three M4 groups and three single-row tails. Q/V/K and gate/up occupy distinct
storage in the ELF, so equal values at different addresses must still hit.
The test revisits Q after FFN-up to verify retained snapshot ownership.

`verification/out/m4-group-replay-20261027-02/result.json` is PASS: 36 checks,
six actual M4 computations, six misses, 12 hits and 18 direct single-row tail
calls. For each group, cached bytes and FCSR/VCSR match actual recomputation;
all output guards match. Each tail uses the installed `quantize_row_q8_K`
function on both sides, without passing through the M4 cache. This exercises
the proposed standalone grouping, not the still-unchanged GGML call site,
threadpool, graph cancellation or a model using the cache. It does not provide
an independent quantizer specification oracle for every group.

QEMU runs with QBS disabled. Log SHA256:
`ac18452bb819711ccce461064de27dffa7d201d87d2a5262f5cf417ffbc8966a`.
All source, library and capture pins are checked before and after execution.
The preceding `m4-group-replay-20261027-01` attempt stopped at compilation on
an array-address comparison warning; it did not execute a guest test.

### RTL preparation-cost experiment

`build_cache_soc.py`, `cache_soc.cpp`, `run_cache_soc.py` and `check.py` define
a same-ELF ABBA comparison on the canonical VCS SoC. Each trial prepares the
same captured four-row input three times. Baseline performs three actual
quantizations; the candidate uses the tested cache, with a cold miss followed
by two exact-value hits. All three output buffers must match the golden bytes,
their guards and FCSR/VCSR requirements. Both paths use the same producer.

The timed candidate includes Newlib heap allocation, CSR handling, one input
snapshot and prepared-result snapshot, two full input comparisons and two
output copies. The standalone allocator is a bounded 128 KiB heap, not an OS
allocator; allocator behavior and library byte-copy speed may differ in Linux.
Cache construction, destruction, UART printing and post-run oracle checks are
outside the timed region. This experiment measures preparation only: it does
not include matrix execution, graph scheduling or establish model speedup.
The candidate must report 49152 requested comparison bytes and 45600 copied
payload bytes per three-call trial; these are software accounting quantities,
not measured DRAM traffic.

The build is `verification/out/m4-cache-soc-build-20261027-03`. Offline
preflight passed. Execution was launched independently as
`m4-cache-soc-20261027-01.service`, with output in
`verification/out/m4-cache-soc-20261027-01`. At launch the actual VCS child
was confirmed executing after source-manifest and image-contract checks.
The worker completed PASS after 34 minutes 50 seconds, including protocol,
guest-result and post-execution identity checks. This is preparation timing,
not model or complete projection timing:

| Trial | Path | First call | Second call | Third call | Total cycles |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0 | Recompute | 115156 | 114785 | 114731 | 344672 |
| 1 | Cache | 149945 | 52952 | 52812 | 255709 |
| 2 | Cache | 148830 | 52818 | 52880 | 254528 |
| 3 | Recompute | 114839 | 114770 | 114726 | 344335 |

Paired totals are 689007 versus 510237 cycles, a 25.946% reduction or 1.3504x
preparation speedup. The first cache fill is more expensive than recomputation;
with no later reuse it is a regression. Therefore, do not install unconditional
cache insertion for every projection merely because this three-call sequence
is beneficial. Admission must target repeated consumers, such as Q/V/K and
gate/up. A lookup miss with no future consumer should quantize normally and
avoid snapshot insertion. Runtime policy and its graph-level cost still need
validation before enabling any production default.

The prototype has not reserved or enlarged hardware SRAM. Its owned copies
use software memory. Every admitted three-call cache trial reports two hits,
one miss, one store, 49152 requested comparison bytes and 45600 copied bytes.
The independent protocol check records 65586 CVXIF requests/responses,
66544 backend allocations/completions, 7256 completed AXI reads and 49152
matched write bursts; none remain pending or aborted. All guest error counts
and contract protocol-error counts are zero. Both source-manifest checks pass.

Log SHA256:
`1ef81a5770e8e51554e234de3457c98a4f769d0b07a23fcc5ffc3c58a2157044`.
UVM result SHA256:
`1116184b510da0ea843ad213e3fb51f091a578ddbb282d1c5a3fdc9634b2478c`.
The accepted ledger is `verification/qbs/m4_prepared_reuse/results-20261027.json`.

### GGML profitability policy candidate

`software/qbs/ggml/m4-reuse-policy.h` is the installed admission helper.
It uses actual GGML graph/tensor APIs and
a caller-provided predicate for supported Q8_K/M4 consumers. The predicate
must include real runtime capability/layout selection; the helper does not
invent a hardware capability from a GGML weight type.

| Position in a matching consumer chain | Lookup | Save a miss |
| --- | --- | --- |
| First, with a future consumer | Yes | Yes |
| Intermediate | Yes | Yes |
| Last, with an earlier matching consumer only | Yes | No |
| Isolated or unsupported | No | No |

The last rule avoids the measured first-fill regression on one-use inputs.
A last-consumer miss should compute normally without allocating a new entry.
The graph scans are bounded at 128 nodes in each direction. Unknown/custom
side-effect boundaries, expert operations, overlapping result writes, other
quantized consumers and incompatible inputs stop the chain. Nonoverlapping
F32/F16 matrix work and metadata-only views may be crossed. Current-node
output aliasing is checked as well as intervening writes. The initial shape
domain is contiguous F32[K,M] with K divisible by 256, M at least four and
no higher-dimensional batches.

This policy estimates useful reuse; it never proves a hit. Exact owned input
bytes and producer/numerical controls remain mandatory. Even when a graph
hint predicts reuse, changes to input contents must cause a miss. Cache
ownership, graph epochs, worker-local state, prefix admission, actual-compute
counters and exception replay remain the integration wrapper's responsibility.
Do not turn this helper into an identity-only cache.

The actual-GGML host test in `test_policy.py` passes 35 checks under UBSan.
It compiles current GGML graph/tensor source instead of using fake tensor
structures or a possibly stale host library. Cases include Q/V/K positions,
different inputs, current/intervening aliases, exact adjacency versus one-byte
overlap, custom writes, float/half gaps, unsupported quantized and expert
consumers, views, strided/small/batched inputs, invalid node selection and a
missing capability predicate. This is policy selection testing, not native
graph execution or a production-model integration result.

### Actual repack call-site candidate

The private `repack_candidate.patch` now connects the policy to GGML's real
`forward_mul_mat` grouping loop. `compile_runtime_candidate.py` copies the
current external `repack.cpp`, applies only this patch and compiles it with
the production compile record. The production source and normal archives
remain unchanged. Its helper is still under `verification/qbs/m4_prepared_reuse`
and must be promoted/consolidated before production installation.

The candidate uses a thread-local owned cache, graph/epoch/source boundaries
and prefix admission for the first eight groups. The current functional
domain additionally requires one GGML worker, enabled M4 preparation and
contiguous, non-wide Q8_K packing with K no greater than 6144. Other worker
counts, K sizes, shapes, packing paths and numerical modes retain the original
quantization call. This limit is a software optimization policy, not a change
to QBS or ordinary RVV hardware support. The capability predicate consults
actual QBS support and activation-layout planning rather than assuming that
every quantized weight selects the same packing.

On a miss, the normal producer is executed once and incoming/generated
FFLAGS are combined. Only an eligible vector result with a future consumer
may be saved. Allocation failure does not run the producer a second time.
A final consumer misses without saving. Input-chain changes clear ownership;
finishing the final consumer releases snapshots. Tails remain direct calls
to the existing single-row converter. No hardware activation-context
reservation is created by this software cache.

`verification/out/m4-runtime-graph-20261027-01/result.json` is PASS. It links
the private repack object with the unchanged normal libraries and compares
cache OFF/ON in 24 actual GGML graph executions. Real captured activations
are used with deterministic test weights. Scenarios cover repeated consumers,
an F32 matrix gap, in-place input writes, custom hidden input writes, two-worker
fallback and non-RNE fallback, each over two changed-input epochs at reused
addresses. All 46272 output/state bytes match. The eligible paired chains
report exactly 12 real vector computations and 12 cache hits; no cache event
appears in the baseline or prohibited scenarios. The graph checker also passes
four host tests covering missing, duplicate and invalid activity evidence.

Graph log SHA256:
`442dec36a1989cbeb21ea92b0bd06a0c2795fa8cfda9abe224d7dc454ce136f6`.

The candidate emits `GGML_RISCV_QBS_M4_CACHE` events with `hit`, `compute_rvv`
or `compute_generic`. The `fill` field is permission to attempt insertion, not
a count of successful stores. Those events distinguish actual work from reuse.
Under this private experiment, the older lifetime report still describes
logical packed-buffer preparation invocations and must not be interpreted as
the number of executed quantizations. Production installation requires an
explicit compatible counter/schema update, not a silent relabeling.

The full-model OFF/ON worker is `m4-runtime-model-20261027-01.service`, output
`verification/out/m4-runtime-model-20261027-01`. QEMU was confirmed executing
and loading the real Qwen2.5-1.5B Q4_K_M model. Both sides retain installed
Decode preparation and cross-op context reuse; only the software M4 cache
changes. The worker compares six full-vocabulary outputs, token and CSR state,
and exact native QBS workload counts with two KV configurations. Its result
is now PASS; QEMU wall time is not a hardware performance metric.

All six comparisons cover 911616 logits in total, with bitwise-equal logits,
tokens and FCSR/VCSR. Both sides execute the same 149448 native QBS commands
per process, with identical per-format shapes, arithmetic work and hardware
context lifetime counts; no emulated commands are used. The software cache
does not reduce the model's matrix arithmetic or claim to replace it.

`audit_model_preparations.py` independently associates each computation/hit
event with its following logical M4 lifetime record, checking graph epoch,
row count and K. All records reconcile:

| Preparation activity per process | Cache OFF | Cache ON |
| --- | ---: | ---: |
| Logical M4 preparations | 386 | 386 |
| Actual M4 producer executions | 386 | 220 |
| Cache hits | 0 | 166 |
| Actual producer executions inside the cache wrapper | 0 | 110 |
| Actual producer executions on the original uncached path | 386 | 110 |
| K1536 producer executions | 332 | 166 |
| K8960 producer executions | 54 | 54 |

The 166 observed duplicate M4 preparations are all removed in this recorded
model execution. The reduction in actual M4 quantization calls is 43.0%, not
a measured model-cycle reduction. In particular, `compute_rvv=110` in the
cache event stream is not the total quantization count: another 110 M4 calls
still execute on the ordinary path. Single-row preparation is outside this
audit. The analysis checks source/library pins and the original worker's
passed result before interpreting activity. Its three tests reject malformed
or unbalanced event/lifetime traces.

Model log SHA256:
`843843bcc5b1fe81f96947527bec54dd0be557fba8a79e8ca3aef2c8860d5bb8`.
Worker result SHA256:
`0e5c89d28e51b008d747eefe9b04041745f52d7a34c6d6614852923bab9609f2`.
Detailed activity is `preparation-audit.json` in the same run directory.
Production sources/archives remain unchanged. The forthcoming vector-byte
successor needs its own acceptance; this result validates only the original
private runtime candidate.

### RVV byte-operation successor

Static inspection of the accepted preparation ELF confirms that cache calls
resolve to scalar `memcmp`/`memcpy` loops. A cache hit includes a 24576-byte
input comparison and a 7008-byte output copy and costs about 52800 cycles in
that experiment. That is the whole hit cost, not a measured function-level
stall breakdown. The successor hypothesis is that these byte operations can
use otherwise available standard RVV resources instead of CVA6 scalar loops.

`software/qbs/ggml/rvv-byte-ops.h` supplies exact byte equality and
nonoverlapping copy with VLA e8/m8 loads, comparisons and stores. Equality
uses the same full-byte/vector-first-mismatch approach as the already checked
integrity helper, not a hash. The helper requires the ordinary RVV C ABI's
zero restart state, clobbers caller-saved vector state, and uses no floating
or saturating operation. No QBS/AKV instruction, hardware capacity, data layout
or quantization rule changes. It is not a global libc replacement.

The standalone helper passes QEMU checks at VLEN 128, 256, 512 and 1024. Each
configuration tests 52 length/alignment combinations, first/middle/last-byte
mismatches, output guards and 256 FFLAGS/VCSR combinations with non-RNE FRM.
Empty/null zero-length cases are included. Logs:

| VLEN | Run suffix under `verification/out/` | Log SHA256 |
| ---: | --- | --- |
| 128 | `m4-byte-ops-v128-20261027-01` | `a7951a6d22b1a1702dc99f285f4b4ef514b072501c7e4e3f22d50bf96954ffa4` |
| 256 | `m4-byte-ops-v256-20261027-01` | `891baf5cd9343bae032c2f0c50bb6ff48587edc0c90c8614ce03f0db21a7d87d` |
| 512 | `m4-byte-ops-v512-20261027-01` | `f14658cb216707ae1d34e2acdc00cc072426ed607804c77a0b9c92c2696f6b2c` |
| 1024 | `m4-byte-ops-v1024-20261027-02` | `2f5d351737ae5034f49aa4f31dc9221f6a2a6188a58ff6215f8edb7bffd4922b` |

`build_vector_cache_soc.py` derives a separate experimental cache header by
replacing precisely two equality checks and three copies. It refuses source
structure drift; all other cache logic remains unchanged. The portable
management path still passes all 8064 UBSan checks, and two generator tests
pass. The earlier model worker's header/object is not modified.

The new VCS build is `verification/out/m4-vector-cache-soc-build-20261027-01`.
Its direct-owned service is `m4-vector-cache-soc-20261027-01.service`, output
`verification/out/m4-vector-cache-soc-20261027-01`. Actual simulator execution
and advancing trace cycles were confirmed after image/source checks. This
run must verify cache bytes, scalar/vector storage interactions and the same
ABBA timing/accounting contract before accepting any additional benefit.
The VCS successor has now completed PASS, including UVM, guest bytes/guards,
accounting and both source-manifest checks:

| Trial | Path | First call | Second call | Third call | Total cycles |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0 | Recompute | 115146 | 114709 | 114739 | 344594 |
| 1 | RVV-byte cache | 121840 | 6933 | 6825 | 135598 |
| 2 | RVV-byte cache | 120906 | 6821 | 6816 | 134543 |
| 3 | Recompute | 114886 | 114708 | 114732 | 344326 |

Paired totals are 688920 versus 270141 cycles: 2.5502x preparation speedup,
or a 60.788% cycle reduction. The same cold-fill scope and construction/
destruction exclusions as the scalar-byte experiment apply. This is not a
whole-projection or model speedup. The earlier scalar-byte cache's independent
pair was 689007 versus 510237; these are separate same-ELF ABBA experiments,
not one three-way experiment. Their matching workload does not make their
raw cycle ratios a substitute for a three-way paired measurement.

The new hit phases cost 6816--6933 cycles; cold fill still costs more than one
recomputation, so consumer-aware admission remains necessary. The added RVV
traffic is not free: the complete run has 63508 AXI read beats versus 44864
in the earlier scalar-byte run. Do not claim less memory traffic solely from
the cycle reduction. Both runs include setup/check traffic outside the timed
regions, and these whole-run counters are not a phase-level traffic breakdown.

The successor protocol result has 66336 CVXIF requests/responses, 67110 backend
allocations/completions, 7580 completed AXI reads and 49266 matched write
bursts, with zero pending/aborted transactions or contract protocol errors.
Log SHA256:
`b624888bc9d40fb3dac25c484bb5e0247254b1404056c2e670cd6d0a3178bc56`.
UVM result SHA256:
`d9869bc7b46fec8154a4c7e1c0477bf4d5694e2f4081feb2b585d218532696ee`.

`compile_vector_runtime_candidate.py` builds the same private GGML call site
and controller with the accepted vector-byte header, without rewriting the
earlier candidate. `run_candidate_runtime.py` provides graph/model gates for
a specified pinned candidate object. The vector-byte runtime is built in
`verification/out/m4-vector-runtime-compile-20261027-01`. Its source/controller
are byte-identical to the preceding private runtime candidate; the shadowed
cache header is byte-identical to the accepted vector-cache VCS header.

`verification/out/m4-vector-runtime-graph-20261027-01/result.json` is PASS:
the same 24 graph executions, 46272 paired output/state bytes, 12 wrapper
computations and 12 hits pass with the vector-byte implementation. Scenarios
retain write barriers, two-worker and non-RNE fallback. Graph log SHA256:
`0047551676261c972e9f94a3797743f8010ed8d344cf25d4880a86f7e81ba2d2`.

The byte helper changes VL/VTYPE, as ordinary RVV C calls may do. The native
QBS SDK issues a memory fence and explicitly selects e32/appropriate LMUL
before each custom matrix command, then sets its output-store geometry.
The dispatcher additionally constructs QBS EW32/VL/EMUL from the command's M,
ignores the ordinary zero-VL check and does not derive its arithmetic shape
from the preceding byte helper. These source checks support safe integration;
they are not a substitute for the pending complete runtime/model gate.

The independent full-model successor is
`m4-vector-runtime-model-20261027-01.service`, output
`verification/out/m4-vector-runtime-model-20261027-01`. Its worker checks model
outputs and actual M4 preparation accounting, requiring the same 386 logical
preparations, 220 actual computations and 166 hits as the accepted scalar-byte
runtime. This successor has completed PASS: all 911616 logits, token/CSR states
and native work agree, with 386 versus 220 actual M4 computations and 166
hits. Model log SHA256:
`fc3b84e5a199da7e1af5278b8a811e15084a6c745be01676320a7d9c949e5fa9`.
Result SHA256:
`8eb2aab7c431a0e5848bb3160843d0fb7501ee1fdda43b6a8f9b59419725b21b`.

### Installed Runtime Integration

The source of truth is `software/qbs/ggml/q8_K-prepared-cache.h` and
`q8_K-prepared-reuse.h`, alongside the shared policy and byte helpers. Promotion
changes namespaces/includes only. The private implementation remains unchanged
as historical evidence. `llama-m4-prepared-reuse.patch` under
`software/qbs/integrations/` contains only this integration and trace-schema
delta: three existing external files and four new headers. Preexisting fork
changes are preserved, not folded into this patch. Its reverse-apply check
passes against the installed tree.

The three previous dirty sources were copied before editing to
`verification/out/m4-prepared-promotion-20261027-01/before/`.
`source-snapshots.json` and `installed-delta.json` record before/after hashes
and scope. Older workers pinning old live sources will now correctly reject
drift; their completed results are historical. Old objects are not relabeled
as newly built or linked into the installed gate.

`verification/out/m4-prepared-installed-build-20261027-01/result.json` is PASS,
covering 892 source inputs and rv64gcv_zfh_zvfh. The installed single-row
quantizer still matches all 177 accepted opcodes. The installed graph gate is
`verification/out/m4-prepared-installed-graph-20261027-01/result.json`, PASS
for 24 graph executions and 46272 paired output/state bytes. Schema versions
and 24 logical records per process are also checked. The link uses only
test/data objects and four normal libraries: no private `candidate.o`, old
quantizer or wrapper override. Graph log SHA256:
`bc85685f196979d470475195b1fa524f9721efd48cdf99d2a0e3152ba0d30d30`.

Cache-enabled lifetime summaries use `SUMMARY_V2`,
`prepared_buffer_invocations` and preparation-time labels. Cache-disabled
logs preserve the original schema. Per-record correlation stays intact.
Three schema tests reject ambiguous names, missing records and inconsistent
counts. Actual M4 work remains independently reconciled from compute/hit
events and uncached conversion traces, not inferred from the logical summary.

The final normal-library model worker is
`m4-prepared-installed-model-20261027-01.service`, output
`verification/out/m4-prepared-installed-model-20261027-01`. Actual QEMU
execution is confirmed. It repeats complete logits/token/CSR/native-work
pairing and checks the summary schema. The installed result is PASS: all
911616 logits, token/CSR states and native work match. Actual M4 computations
remain 386 versus 220 with 166 hits; logical preparation records are 844 in
both processes, separately reconciled under summary schema 1/2. No object
overrides are linked. Installed model log SHA256:
`941cc6c4bfc027506c53e421a81f9cb70e211c091a69b4f40076d254563c310d`.
The cache is off by default; request it with both
`GGML_RISCV_QBS_M4_PREPARE=1` and `GGML_RISCV_QBS_M4_CACHE=1`.

1. Completed for the independent prototype: bounded owned snapshots, exact
   shape/layout/control keys, allocation failure and invalid-mode rejection.
   The accepted implementation is installed behind an off-by-default switch.
2. Completed for byte-cache management and the real-data replay checks above.
   Actual 15-row GGML grouping/tails pass private and installed graph gates.
3. Preparation-only VCS pairs pass with cold fill and byte/CSR costs included.
   They do not measure a complete projection including graph-policy overhead.
4. Opt-in integration distinguishes logical preparation from actual work.
   Private full-model activity removes the observed duplicate M4 preparations.
5. Normal-library graph and model gates pass.
   Broader Prefill batches/worker-policy expansion require separate evidence.
   Hardware context reservations and SRAM size remain unchanged.
