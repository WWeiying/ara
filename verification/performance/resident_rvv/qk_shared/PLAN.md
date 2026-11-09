# Shared QK Execution: Source-Grounded Integration Plan

This is a design contract, not implemented QK RTL or an accepted ISA. Production
sources remain sealed while PV smoke/performance consumers run. QK changes are
gated by their results. No bus, DDR, frequency, lane-count or MAC-array change
is part of this plan.

## What Is Actually Present

| Resource | Current implementation | QK treatment |
| --- | --- | --- |
| Lane FPU | `vmfpu.sv:i_fpnew_bulk`, 64-bit SIMD, native FP16/FP32 units | Borrow the same instance; add a held private format mode, not another FPU |
| Private sums | `akv_resident_pv_lane.sv:accum_q[16]`, 64 bits/slot/lane | Reuse the same 512 B across four lanes for FP32 scores |
| Coefficient supply | `akv_resident_pv_import.sv` holds eight pairs in existing StA queue heads | There is **no** private 256 B probability table to reuse or subtract from area |
| Raw reader FIFO | `akv_resident_pv_reader.sv:data_q[2]`, 256 bits/entry | Candidate reuse as two 16-dimension Q blocks, one per head |
| Query store | `akv_q_store.sv`, existing 2 KiB, synchronous 256-bit read | Read two head blocks without overwriting persistent Q |
| K column panel | `akv_v2_context.sv:column_data_q[4]`, 1024 bits/column | Retain the existing gather/capture store; select slices, do not duplicate it |
| Payload elasticity | Existing 256-bit fanout and lane-local two-entry input FIFOs | Hold K slices and coefficient packets while lanes accept them independently |
| Commit/ownership | Drain, all-lane acquisition, result barrier, LDU final debt, release | Extend the proven PV mechanism, never disable native hazards |

The two Q blocks total 64 B and fit the current reader FIFO's physical capacity.
This reuse is only real if the eventual RTL has one array shared by modes.
Instantiating a Q buffer beside an unchanged V FIFO would add 64 B and must be
reported as such. Similarly, QK and PV must not have separate accumulator arrays.

## Ordered Computation And Geometry

For each active head and token, compute positive-FP32-zero followed by D FP32
FMAs in increasing dimension order, using exact F16-to-F32 input widening.
Scaling, mask addition and softmax remain in their original software locations.
No tree reduction, zero skipping, lower precision or reassociation is permitted.

Preserve the existing token-to-lane mapping `lane = token % 4`. Lane `l` has
`n_l = max(0, ceil((T-l)/4))` active FP32 elements. Each head needs
`ceil(n_l/2)` 64-bit words. Thus T64/H2 needs 16 slots per lane, exactly the PV
array capacity; T9/H2 needs 4 slots in lane 0 and 2 in each other lane.

The destination remains four clobberable vector registers, but its internal
view is EW32/VL128/LMUL4. Head stride is 64 FP32 elements, eight words per lane.
Word addresses are `vaddr(vd) + 8*head + word`. A partial final FP32 word uses
`be=0x0f`, not the full-word mask used by admitted PV shapes. Inactive lanes and
inactive tail elements must generate neither writes nor FP exceptions.

For T1 only lane 0 computes. Acquire all four physical FPUs for the bounded
lease if this keeps ownership simple, but start/commit only active controllers.
An inactive controller must not wait for a nonexistent first result. The group
barrier uses an explicit active-lane mask, and release still drains every owner.

A K packet contains 16 tokens, four F16 values per lane. Keep the existing EW16
shuffle: lane `l` receives offsets `{l,l+8,l+4,l+12}`. Widen physical halfwords
`{0,2}` first, then `{1,3}`, as native `OpQueueConversionWideFP2` does; widening
the low/high 32-bit halves directly would exchange tokens 4 and 8. One packet
therefore updates two FP32 score words per head, subject to each lane's tail.

The final packet need not reach every otherwise active lane. At T17, lane 0
needs two raw packets but lanes 1..3 need one. Qualify each packet's fanout mask
with `16*packet + lane < T`, and give each lane its own `ceil(n_l/4)` raw-packet
count. Otherwise an inactive final packet or the next coefficient can strand
the per-lane parser. The geometry tests bind both shuffles to the current RTL
constant tables and enumerate every T1..T64 output location.

## Query Identity Must Be Explicit

An AKV context may contain up to eight query rows. A QK command that always
reads rows 0/1 would only support the first pair and is not an acceptable generic
integration. Carry a three-bit query-base selector and validate
`query_base + H <= resident_q_rows` before mutation.

One candidate encoding is custom-2/funct3=7/funct7=3, reserved rs2=0, vector rd,
and scalar rs1 with T-1/H-1/D in bits 8:0 plus query-base in bits 11:9. All upper
bits are reserved zero. This is a proposal; allocation must go through the ABI
JSON/generator and both decoder stages. No scalar rs2 or integer rd is implied.
The existing PV encoding is unchanged. Capability index 4 stays zero until the
combined contract, correctness, representative benefit and fallback are accepted.

## Bounded Dataflow Without Another Wide Port

1. After ordinary work drains, validate context, Q base, D/T/H, FP state, frm,
   vstart and destination. Hold the original CPU transaction through completion.
2. Seed active accumulator slots with FP32 zero through the existing private
   payload/seed handshake, rather than adding a reset/multiwrite port to the array.
3. Read a 16-dimension Q block per head into the two existing reader entries.
   Use the Q store's synchronous response protocol; do not assume combinational
   data or alias it onto the K/V row selector.
4. Launch the existing four-column K collector. Q reads are finished before
   column start, preserving `akv_unified_context`'s conflict rules. Do not delete
   its legacy-read/column-busy exclusion merely because Q has separate SRAM.
5. For each dimension, broadcast one F16 query pair over the existing payload
   wires, followed by the current K column's 256-bit slices. The registered
   column store supplies those slices; no new 512 B panel buffer is needed.
6. Each lane widens a K word in two FP32 subwords and issues one/two heads.
   Advance word/head/dimension only on accepted FMA inputs. Per-slot pending
   state prevents reading a sum before its previous returned value.
7. Reuse the Q block for four consecutive panels. Reload at the 16-dimension
   boundary only after prior coefficient packets have been captured by the
   fanout/lanes. Already accepted FMA inputs need no live reference to old Q.
8. New column gathering may overwrite the panel after its last slice has been
   captured downstream; it need not wait for all old FMA returns. Never overwrite
   an uncaptured slice or let a new coefficient overtake old K data in lane FIFOs.
9. Drain accepted arithmetic, pass the active-lane result barrier, write each
   active score once, drain true final VRF acknowledgements, then release/reply.

The existing 256-bit raw resident interface may select Q responses and registered
column slices by a private mode. External AXI and the existing LDU data width
remain unchanged. A row/column/request response must have explicit ownership
and timing; a combinational mux alone is not a transaction protocol.

## Widening, Masks And Flags

The private VMFPU endpoint currently hardcodes FP16. FP32 requires a held format
selector, two active SIMD elements, FP32 accumulator word masks and matching
result writes. Format cannot change with outstanding private results.

FPnew's parallel-format slice samples mask bits at a format-dependent stride.
With four physical mask positions, the FP32 unit consumes positions 0 and 2,
not positions 0 and 1. Expand two QK element-mask bits to `{m1,m1,m0,m0}` before
the existing interface (and use the corresponding stride when FP8 is enabled).
Passing `0011` for two active FP32 elements would disable the second element;
tail-mask mistakes can also raise exceptions from inactive values. The host
geometry contract in this directory tests this explicit sampling rule.

`ara_pkg::fp32_from_fp16` quiets NaNs without returning exception flags. Reusing
only that bit conversion would lose signaling-NaN NV. Preserve active-input
signaling information and accrue NV on the corresponding accepted operation, or
use the existing FPU conversion path with explicit accounting. Inactive K tails
and unused heads must not raise NV. Existing native VFWMACC behavior is not
assumed correct merely because it provides a convenient conversion function.

The preferred first implementation is internal widening that preserves NaN
class: use the existing finite/subnormal re-encoding, but map a NaN mantissa as
`{f16.m,13'b0}` instead of canonicalizing it. The existing FP32 FMA then observes
sNaN and produces NV itself under its real active-element mask. This is not an
architectural conversion instruction whose NaN result must be exposed. Do not
just clear the quiet bit of the helper's canonical NaN: its remaining payload
is zero, which would turn it into infinity. Test this option against independent
SoftFloat cast-plus-FMA results/flags before choosing it over explicit NV carry.

Use `ordered_reference.py:OrderedReference.qk`, backed by independent Spike
SoftFloat, for final FP32 bits and flags. Cover subnormals, signed zero,
infinities, qNaN/sNaN, all admitted rounding modes and prior sticky flags.

## Execution Gates

1. Accept PV smoke, same-binary ABBA against strong rotation, and selected
   production-SoC geometry/legality regressions. Preserve the original evidence.
2. Before editing production files, finish every consumer whose source pins
   include them. Frozen copies do not authorize altering pinned originals.
3. Implement one shared arithmetic/store controller and private format mode.
   Validate Q base, inactive lanes, tail byte enables and owner transitions.
4. Run one discriminating real QK tile, then a complete real-model call with
   QK+PV. Compare identical work and original arithmetic order, not local FPU
   service time against an entire software helper.
5. Admit cross-shape runtime selection only after stable complete-call benefit.
   Ordinary RVV/QBS and unsupported models/shapes retain their existing paths.

The measured old QK work is 9901 cycles for D128/H2/T137. Its average lane work
is not a latency floor. Keeping this mapping gives busiest-lane issue counts
2048+2048+512=4608, before supply, widening, drain and ownership. Short T/H can
be recurrence-limited; no plan promises one FMA per cycle for every shape.
