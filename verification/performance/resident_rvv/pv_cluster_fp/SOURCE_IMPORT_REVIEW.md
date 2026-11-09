# Source import before committing an instruction ABI

The four-lane numerical gate supplies prepared seeds and coefficients through
the controller ports. It does not measure their architectural VRF import cost.
The instruction proposal in `pv_vmfpu/SOC_INTEGRATION.md` is still a proposal;
do not expose a capability or fix an encoding/layout before checking this path.

## Storage consequence of the current proposal

For D128/H2/T64 with four lanes, seeds occupy 512 bytes and FP16 coefficients
occupy 256 bytes. The six-register import therefore transfers 768 bytes, or 24
64-bit words per lane. These are derived capacities, not synthesis areas.

The earlier coefficients-first, head-major layout requires buffering coefficients
until all seeds have arrived. A fully streamed implementation cannot simply drop
this storage: token t needs both heads' coefficients, and the source request
delivers the entire first head before the second head.

## Lower-storage alternative to evaluate

Keep the six-register size, but import seeds first and interleave the two FP16
coefficients of each token in the remaining two registers. For a one-head
operation, the second coefficient is inactive and must not raise FP exceptions.
One 256-bit native read group then contains eight token coefficient pairs.
After undoing the EW16 shuffle, hold this group until eight token rows have
consumed it. Backpressure the existing source operand queue instead of storing
all 64 pairs in a new coefficient array. The group itself needs 32 bytes rather
than 256 bytes, excluding its pending masks and control registers.

This is an architectural source-layout choice, not a bus-width change, and it
does not change the ordered FP16 recurrence. It remains unimplemented. Software
must prepare the interleaved coefficients; that packing cost belongs in the
full-call comparison. Neither reduced storage nor a theoretical bandwidth is
evidence of a net speedup.

Before selecting it, check:

1. Source import can remain outstanding while private computation proceeds,
   without blocking the same path needed for V context reads or final writes.
2. The source requester preserves all six registers' hazards and layout metadata
   until consumed; destination aliasing is rejected, not bypassed.
3. Per-lane source acknowledgments and EW16 unshuffle produce exactly one paired
   coefficient for each token, including T=1 and T=9 tails.
4. The context SRAM output and coefficient hold register cannot overwrite an
   unaccepted packet. Use existing operand buffering where it provides the same
   ownership/credit guarantee; do not duplicate the tested transport FIFO blindly.
5. Partial seed import or coefficient exhaustion cancels before any final write;
   the all-lane barrier and outstanding final-write accounting remain mandatory.
6. Include conversion, interleaving, seed rescale, import, ownership and final
   drain in real-model complete-call timing, against rotation-and-loop RVV.

The numerical gate deliberately leaves this ABI choice open. Its prepared
operand corpus is valid for either ordering because token order and seeds are
unchanged; it must not be cited as verification of the import layout itself.
