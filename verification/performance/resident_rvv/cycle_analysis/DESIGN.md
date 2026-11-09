# Bounded resident execution: implementation decision record

Status: architectural preparation, not implemented RTL or an accepted new ISA.
The measured baseline and decision gates are in `README.md`. The running PV
register-rotation control must finish before choosing a datapath modification.
Keep existing bus widths, memory timing, lane count and arithmetic resources.

## What the command would replace

The accepted paired PV helper first rescales two FP16 accumulator vectors.
For each token, it converts two probabilities from FP32 to FP16, replays one
resident V row into the VRF, and issues two token-ordered FP16 FMAs. The next
V row overwrites the same source registers. A resident command would keep
those accumulators local for one bounded tile and feed the **same lane FPUs**
from the resident V stream. It would not implement softmax, change the cache
layout, introduce a reduction tree, or add multipliers.

Correct arithmetic per head and dimension remains:

```text
acc = FP16_mul(old_acc, FP16(old_scale))   // once per original tile
for token in increasing order:
    acc = FP16_fma(FP16(probability[token]), V[token, dimension], acc)
```

Every conversion, multiply and FMA keeps the original rounding and flag
semantics. In particular, no zero-coefficient skipping, FP32 accumulation,
tree summation, or reassociation is allowed. Separate accumulator elements
can interleave, but updates to one element must use its latest returned value.

## Existing RTL that must remain authoritative

| Responsibility | Current site | Required treatment |
| --- | --- | --- |
| Blocking custom command | `ara_dispatcher.sv`, QBS custom2 decode | Drain older work; retain CPU transaction identity until terminal response |
| Register dependencies | `ara_sequencer.sv`, access tables/read masks | Reserve all seed/coefficient sources and destination groups explicitly |
| VRF source reads | `lane_sequencer.sv`, QBACC `StA` request | Reuse a defined operand stream; source length is not automatically destination length |
| Resident storage | `akv_unified_context.sv` and `akv_v2_context.sv` | Keep Q persistent across refills; retain existing single-port bank arbitration |
| Resident payload delivery | `akv_engine.sv`, shuffled LDU result wires | Private delivery is a separately qualified mode, not a fake architectural VRF write |
| Arithmetic | `vmfpu.sv`, `i_fpnew_bulk` | Borrow existing instance; keep current `SharedFma` selection and latency configuration |
| Ordinary result attribution | `vmfpu.sv`, processing queue and result queue | Resident results go to a distinct local sink, never through an unrelated RVV queue entry |
| FP legality | `cva6_accel_first_pass_decoder.sv` | Mark the new operation as FP; enforce FS legality and normal FP state tracking |
| Flags and completion | Lane flag path, dispatcher, sequencer | Publish accepted active-element flags before terminal completion; inactive owner contributes zero |

`mfpu_ready_o` reports queue capacity, not a drained execution unit. Owner
acquisition needs a checked quiescent predicate covering issue, processing,
commit, operand requests, result queues, FPU in-flight outputs and pending flags.
Completion needs the reverse: all resident arithmetic returned, final VRF
writes granted, flags published, then owner released. Context refill/release
must not occur while the owner is active.

Existing AKV row/column commands already early-acknowledge and overlap following
FMAs. Their behavior must remain unchanged. Do not remove the multiple-reader
WAR gate to make the new experiment faster.

## Storage and transport must be budgeted together

Two D128 FP16 accumulators require **512 B total**, or 16 64-bit slots per lane.
Two sets of 64 FP16 probabilities contain **256 B logically**. That is not
automatically 256 B of hardware: four replicated lane-local copies would cost
1 KiB. The following are alternatives, not simultaneous allocations:

| Transport option | Benefit | Cost requiring measurement |
| --- | --- | --- |
| Central 256 B coefficient store, mode-qualified broadcast over existing LDU data wires | No new wide data bus; one logical copy | A coefficient delivery beat per token; central source collection and lane mode control |
| Sixteen-token subcommands with replicated lane coefficients | Small bounded local stores, simple consumption | More commands, packing, accumulator imports/exports; old-scale multiply must still occur only once per original tile |
| Full-tile lane replication | Simple local coefficient reads | 1 KiB physical coefficient storage plus packing; not the preferred starting point |

A possible way to supply the first option without adding another lane-to-VLSU
port is a packed VRF source group consumed by the existing `StA` stream:
256 B coefficients followed by 512 B already-rescaled seeds. A source group
large enough for six registers and a four-register destination would need
different, explicit read/write geometries. This is an **uncommitted transport
proposal**, not a finalized instruction format. Packing, conversions, register
pressure and all 768 B of import work belong in the complete-call comparison.
Do not assume that the current QBACC request geometry implements this layout.

V ingress may need one or two words per lane to hold data until both head
operands are accepted. That is 32 or 64 B in addition to coefficient and
accumulator storage. Count valid bits, pending-slot bits and any in-flight
ledger as well. These are storage bounds, not synthesized area claims.

Keep service identity in an explicit preserved tag or a bounded handshake
ledger. `AddmulTagKeepMask` discards `operand_a`, and simulation-only debug IDs
are absent after synthesis; neither can be the ownership contract. Valid data
must remain stable under FPU input/output backpressure. Advance token/word/head
positions only on the corresponding accepted transaction, not a fixed latency
guess. A pending accumulator slot cannot be read before its preceding result.

## Admission and fallback

First prototype: four lanes, VLEN1024, D128, paired heads, a bounded nonempty
tile up to 64 tokens, no mask, `vstart=0`, and a valid F16 resident context.
This narrow prototype is not the final coverage claim. Before runtime selection,
cover D64/D96/D128, single and paired heads, and short/full/tail tiles. Keep
software grouping/segmentation and ordinary native-auto/RVV fallback for other
shapes. Do not claim direct D256 or other numeric formats.

All context, register-range, alignment and FP-mode checks precede architectural
destination mutation. Snapshot the active rounding mode for the command, or
initially advertise only the verified RNE capability and fall back otherwise.
There is no silent software retry after a partial destination update. The local
accumulator is ephemeral: nothing survives a completed command that the next
caller could consume accidentally.

The custom2 funct3 space is already occupied. Any eventual encoding must be
assigned through the ABI source/generator with a capability bit and matching
SDK/decoder tests; a private `.word` is not a finished software contract.

## QK is a second gate

The same 512 B can hold two FP32 score rows of up to 64 tokens, since QK and PV
are not active together. Keep dimension order and existing K-column gathering.
Q remains in the dedicated Q store; it must not be overwritten by PV coefficients.
Q distribution, gather pauses and tail handling must be measured, not assumed
free. Existing widening FMA explicitly converts scalar and vector FP16 operands
to FP32 representations; reuse its subnormal/NaN behavior and inactive-element
masking rather than directly feeding F16 bit patterns into FP32 arithmetic.

## Acceptance sequence

1. Accept the software control, including the separate strict CSV audit. Use its
   implementation performance, not the earlier single-head generic baseline,
   as the hardware comparison. Loop-layout effects are not isolated WAR savings.
2. Fix coefficient/seed transport and estimate its explicit cycles and storage.
   If that erases the remaining full-call opportunity, record the negative
   decision instead of adding a service controller.
3. Validate any selected PV controller with an independent ordered reference:
   random bounded ready stalls, short tiles, tail byte enables, reset/drain,
   NaNs/infinities/subnormals/signed zeros, flags, and admitted rounding modes.
   Then run the same real Qwen3 complete call in VCS and ordinary-RVV/QBS
   regressions. A controller-only test is not SoC acceptance.
4. Extend the proven ownership/data path to QK and additional shapes, using the
   same numerical and complete-call gates. Do not combine unrelated optimizations
   into the first attribution experiment.
5. Integrate only reproducible, cross-shape benefits into a shared llama.cpp/SDK
   helper with capability/shape selection and unchanged fallback. No synthesis
   or FPGA deployment is authorized by this experiment.
