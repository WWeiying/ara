# Four-row prepared-activation reuse: investigation and design

This is a prospective optimization, not an installed runtime cache. The
completed Decode/reuse optimization remains unchanged.

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
general multi-group inputs. No cache size has been committed to production.

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

### Experimental cache implementation

`verification/qbs/m4_prepared_reuse/value_cache.hpp` now implements the
independent prototype. It is not included by production llama.cpp. Each entry
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
No timing result is yet accepted. The worker automatically performs protocol,
guest-result and post-execution identity checks; success is not inferred from
launch or partial UART output.

1. Completed for the independent prototype: bounded owned snapshots, exact
   shape/layout/control keys, allocation failure and invalid-mode rejection.
   Production remains unchanged.
2. Completed for byte-cache management and the real-data replay checks above.
   Runtime multi-group and nonmultiples-of-four tail tests remain necessary
   when integrating the cache at the actual GGML call site.
3. Measure real-data miss plus repeated-hit sequences on VCS, counting input
   comparisons, snapshots, copies and flag handling inside the timed region.
   Do not benchmark only an artificially prefilled cache.
4. Retain only a reproducibly beneficial policy. Then integrate with explicit
   counters for real quantizations, cache copies and bytes compared/copied;
   do not present logical preparation events as executed arithmetic.
5. Repeat normal-library graph/model gates, including multi-group Prefill,
   standard fallback and existing M1 hardware-context reuse. The software
   cache must not reserve or imply validity of the hardware context.
