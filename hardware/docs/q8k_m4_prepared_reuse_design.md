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

1. Implement a bounded experimental value-checked cache with independently
   owned input/output snapshots, exact shape/layout/control keys and strict
   allocation-failure/unsupported-mode fallback. Keep production unchanged.
2. Test mutations at first/middle/last bytes, reused addresses, distinct
   buffers with equal values, changed shape/control, eviction and repeated
   groups. Test nonmultiples-of-four through the unchanged tail path.
3. Measure real-data miss plus repeated-hit sequences on VCS, counting input
   comparisons, snapshots, copies and flag handling inside the timed region.
   Do not benchmark only an artificially prefilled cache.
4. Retain only a reproducibly beneficial policy. Then integrate with explicit
   counters for real quantizations, cache copies and bytes compared/copied;
   do not present logical preparation events as executed arithmetic.
5. Repeat normal-library graph/model gates, including multi-group Prefill,
   standard fallback and existing M1 hardware-context reuse. The software
   cache must not reserve or imply validity of the hardware context.
