# Unordered Widening Reduction Investigation

Pre-patch hypothesis: after all source elements have been consumed, a pair of
valid partial sums is merged with a stale source predicate. `issue_be` and
the input/output `tag.flag_mask` can be zero even for +Inf plus -Inf. Real FMA
NV should then be discarded by FPnew status collapse. Separately, inter-lane
and SIMD merges inherit zero `issue_be` from the combinational default.

Probe source-consumption enable/count, work issue/processing counts, first
operation, neutral-filling state, mask, converted operand, selected A/B/C,
control/flag tags, FP input/output acceptance, raw per-slot FMA/noncomp status,
collapsed/gated status, registered exception events, lane activity and reduction
transport handshakes. All-masked and remote-active signaling-NaN seeds are
required controls: eagerly exposing initial seed exceptions is not valid for
an empty active set; suppressing them with local source activity loses them
when only another lane contributes. FP16 first SIMD fold needs two physical
low FP slots, not only element zero.

The successor bench instantiates real source and seed operand queues, including
FP32-to-FP64 re-encoding and lane-specific seed neutralization, and four real
VMFPUs/FPnew units. It models predicate delivery and buffered slide transport
(ordered chain or three-round reduction tree). No internal forcing, CPU, CSR,
MASKU, dispatcher, sequencer, VRF, or SLDU controller is instantiated. Exact
result writeback and sticky flags from actual VMFPU exception outputs are
checked using the dispatcher's OR-of-all-lanes data and OR-of-valid contract.
Consecutive cases run without reset. Extended cases queue ordinary VFADD behind
an unfinished reduction and check its results, flags and ownership separately.
It is not a full ELF replay or whole-image signoff.

The default baseline is the parent's immutable final01 source snapshot.
`run.py --out NEW_DIRECTORY [--vmfpu PATH] [--extended] [--deferred-flags]` makes independent
read-only source snapshots and performs one bounded VCS build and run.
The older ordered_reduction runner and bench are not edited. Compile input
ordering is read from its previous passing command manifest, then every RTL
source is pinned from final01 (except an explicitly selected VMFPU).

`--deferred-flags` checks one unordered publication per lane, no later than local
done; ordinary and ordered results retain per-FP-output events. The 80 extended
cases cover the original sparse widening values, intra/inter/SIMD cancellation,
FP16 first-fold upper-slot NV, neutral-fill bubbles, FP16 widening, FP16/32/64
seed sNaNs, all-masked seed copies, remote/late activity, min/max, predicate/tail
poison, unmasked finite data, VL 34/65/129, five rounding modes, sticky flags,
and queued ordinary operations. The four-lane transport is modeled, so this
does not validate arbitrary SLDU timing, sequencer epochs, CSR timing in a CPU,
other lane counts, or FP8.

Candidate implementation separates source activity from internal arithmetic
masking. Predicate/tail-neutralized intra/inter-lane operands enable all slots;
pure neutral injection enables none. SIMD folds enable physical low bytes
`0f`, then `03`, then `01` as applicable. Pending unordered flags are published
on entry to MFPU_WAIT and discarded for a globally empty reduction. No result,
operand, work-count or transport scheduling change is made.

Compare identical case sets with:

```sh
python3 -B verification/fpga/current_board_review/ordered_reduction/unordered_widening/analyze.py BEFORE AFTER --out REPORT.json
```

This pairs every accepted FP operation/output, extracts raw NV evidence, checks
invalid flag buses, and compares numeric results and completion cycles. Full
integration replay remains the parent's responsibility; no full image is built
by this runner.
