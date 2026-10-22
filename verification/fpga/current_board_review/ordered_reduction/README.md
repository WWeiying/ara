# Ordered FP Reduction NV Coordinate Regression

Measured outcome: see [MEASURED_20261010.md](MEASURED_20261010.md).
Current and deployed sparse cases fail before the fix; the repaired extended
suite passes 166/166 with unchanged result bits and paired cycle counts.

## Pre-run hypothesis

The deployed and current OSUM paths compact source local element 1 from byte
4 to byte 0, but use `be(1, vsew) & mask_i` without compacting the mask.
For mask `f0` (FP32) or `30` (FP16), the element is active but `issue_be=0`.
The first selected negative infinity in original scenario 3 / mask `0x24`
is global element 5: lane 1, local element 1. Its accumulator is +Inf.
Prediction: its raw low-slot FMA status is NV and its result is canonical NaN,
but its output lane mask and tag are zero, suppressing the architectural NV.

Alternative hypotheses are operand/order corruption, no FP acceptance, or
failure to deliver otherwise-correct flags. The trace records accepted B/C,
local selector, byte mask, `issue_be`, input/output tag mask, raw low-slot FMA
status, FPnew collapsed status, VMFPU gated status, registered flag events,
slide transfers, architectural write and completion. Checks require exactly
one instruction/seed/completion per lane, all operand words/masks consumed,
one FP completion and flag event per active element, VL slide transfers and
one correctly addressed destination write with only element-zero BE.

## Scope and oracle

Four real VMFPUs instantiate real FPnew, configured as four lanes
and VLEN=1024. The harness models ordered slide transport and operand/mask
delivery, with no forces or internal state injection. It does NOT instantiate
the CPU, CSR file, dispatcher, sequencer, MASKU, SLDU, operand requester or VRF.
The destination is checked at the VMFPU writeback interface; architectural
sticky flags are modeled by ORing each valid `fflags_ex_o` with initial flags.
This is a reduced RTL regression, not an ELF, full-program or board signoff.
The transport includes the same per-lane spill-register primitive used on
SLDU inputs; synthetic stalls apply after these input buffers. Removing that
buffer changes the VMFPU boundary contract and is not the production topology.

The handoff's original scenario-3 seed and inputs are exact IEEE +Inf/-Inf
bits. Any selected -Inf with the +Inf seed produces canonical NaN and NV.
All-off preserves the +Inf seed and initial flags. First-local-slot and
unmasked controls distinguish mask coordinates. Extended cases cover the
eleven original reduced trial lengths, all five rounding modes and prior NX,
every FP16/32 local slot, partial final words, inactive sNaN, positive-only,
all-on and exact finite sums with slide/writeback stalls. LMUL decoding is
outside this boundary; original LMUL labels select original VL only.

## Running

From the integration worktree, choose a new independent output directory:

```sh
python3 -B verification/fpga/current_board_review/ordered_reduction/run.py \
  --out /tmp/ordered-reduction-current-01 --fsdb
```

`--vmfpu PATH` selects deployed or frozen baseline VMFPU without changing the
worktree. All other dependencies remain current and are hashed in `pins.json`.
`--extended` selects the wider reduced regression. No shared helper is edited.
One build (300 seconds maximum) and one run (120 seconds maximum) per command;
no retry loops. CSV sampling is rising-edge pre-NBA. FSDB dumps top-level
aliases only, bounded by the case list and 10,000-cycle per-case watchdog.
The runner returns nonzero for actual architectural mismatches, even expected
baseline defects. A reproduced failure is never labeled a DUT pass.
