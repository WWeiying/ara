# Bounded resident execution: implementation decision record

Status: isolated lane-controller prototype; no production wiring or accepted ISA.
The measured baseline and decision gates are in `README.md`. The PV
register-rotation control and independent lifetime audit have passed.
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

Global commit is not merely four independent lane completions. The parent must
hold all external write-valid signals until every active lane is ready to commit
successfully. A peer error cancels the other lanes' still-private work and
drains accepted FMA returns. Once an external write becomes irrevocable (which
can precede its final acknowledgment when buffering exists), the parent must
lock out abort. The component's first-final-ack guard alone is insufficient
to establish that SoC boundary. Native result/flag consumers remain gated while
the service owns the FPU; service flag data is zero outside qualified completion.

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

The selected preparation candidate is ordinary vector narrowing, not a scalar
load/convert/store loop. Load the two probability rows under `e32,m2` into
`v16:v17` and `v18:v19`; narrow under `e16,m1` into `v8` and `v9`, with VL equal
to the actual tile length. Load and rescale the old sums directly in
`v10:v11` and `v12:v13`. Then reserve `v8:v15`, consume the six-register source
footprint, and commit final sums into `v0:v3`. Narrowing itself must not use
LMUL8: its wide source would require an illegal EMUL16. If old sums remain in
`v0:v3`, two aligned `vmv2r.v` copies are an alternative cost; a four-register
move to v10 is misaligned.

For a short tile, convert only its active probabilities. Importing the fixed
source footprint is permissible only if unused coefficient entries are never
consumed or included in arithmetic flags. The central collector must undo the
native EW16 permutation and pair corresponding entries from the two head-major
registers. Those are explicit collector operations, not a free prepacked input.

Against the measured rotation control, PV occupies 4411 of 34213.5 cycles.
For its 64+64+9 tokens, 2192 FMA issue beats plus 137 coefficient-consumption
cycles are the controller's optimistic arithmetic/packet floor. Adding 72
fixed-footprint import beats, 48 seed-multiply beats and 48 commit beats gives
2497 service cycles, before preparation loads/conversions, instruction supply,
ownership transitions and stalls. That leaves 1914 cycles before break-even,
not 1914 measured saved cycles. A private two-cycle read/deliver schedule is
structurally compatible with the existing one-port, latency-one context SRAM;
the present architectural replay has three-cycle pacing and is not silently
changed by this estimate. Keeping that pacing leaves a much smaller margin.

Vector preparation across those tiles reads 1096 useful F32 bytes (70 aligned
128-bit AXI data beats), consumes 36 narrowing input beats on the busiest lane,
and writes 18 narrowed words per lane. Optional seed copies add 48 words per
lane. These are service counts, not additive measured latency: some stages can
overlap, while cache response, queueing and drains cost additional cycles.
Full-call RTL timing must decide whether the private mode justifies integration.

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

For the central-store option, one possible ordering is a coefficient packet
followed by the V words of that token, all over the same existing payload wires.
Each lane needs only the current two FP16 coefficients, not the whole table.
The coefficient packet is accepted only after all FMA inputs still using the
previous coefficients have handshaken. In-flight arithmetic results may remain,
but a pending accumulator slot must still prevent reuse of a stale sum.
One extra coefficient beat per token is a real throughput cost. Independent
lane backpressure must not let a coefficient update overtake old V operands.

Because ownership is exclusive and drained at both transitions, a service
could reuse the preserved `control` tag bits as an accumulator-slot index,
instead of enlarging every FPU pipeline tag. This is valid only if native
processing is completely gated out during service ownership, and owner release
waits for every service output. An explicit owner-tag extension is the safer
alternative if that quiescence property cannot be proved. Neither approach may
use the pruned `operand_a` tag or simulation-only identity fields.

No throughput claim assumes a fixed three-cycle or four-cycle return: normal
ready/valid backpressure can extend it, and the optional shared-FMA
implementation has a different latency configuration. Per-slot pending state
and result identity must govern accumulator readiness in either configuration.

## Admission and fallback

First prototype: four lanes, VLEN1024, D128, paired heads, a bounded nonempty
tile up to 64 tokens, no mask, `vstart=0`, and a valid F16 resident context.
This narrow prototype is not the final coverage claim. Before runtime selection,
cover D64/D96/D128, single and paired heads, and short/full/tail tiles. Keep
software grouping/segmentation and ordinary native-auto/RVV fallback for other
shapes. Do not claim direct D256 or other numeric formats.

The isolated controller in `../pv_unit` tests up to 32 FP16 elements per lane,
one or two heads, and 1..64 tokens. Its arithmetic interface deliberately has
no internal multiplier. Passing this component does not implement the parent
owner, instruction decoder, central coefficient source or context transport.

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
