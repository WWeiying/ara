# Frozen-image comparison cycle proof

Captured with real SoC VMFPU + MASKU, external ELF stimulus only. No force,
internal injection, RTL edit, or image rebuild. `capture_current.py` validates
the retained image with the pinned integration runner before and after capture.
Source/ELF/image identities and commands are in each capture directory.

The initial whole-hierarchy VCD conversion eventually finished, but is not the
decode input. `convert_selected.py` uses explicit profile `-s` names,
`-compacttree`, and `-bt 16200ns -et 16600ns`. `selected.vcd` is complete and
49 KB for the baseline. `decode_cycle.py` samples immediately BEFORE rising
edges; times below are ns, not architectural instruction retirement cycles.

## All-off: measured failure

`cycle_before02/{status.json,selected.vcd,cycles.json,cycles.csv}`.
Target `vmfeq.vv v24,v8,v16,v0.t`, PC `0x80000902`, encoding `0x60881c57`.
Architectural flags expected 0, observed 16. Data/setup checks pass.

| Edge ns | Measured event |
| --- | --- |
| 16425.5 | Lane1 FP accept valid/ready=1/1; queued id=0, vm=1, local VL=2; BE=0x33; A=0x0000400000008000, B=0x10007c557bffbc00 |
| 16426.5 | FP return valid/ready=1/1; raw FP16 NV slots [3:0]=0100, lane_masks=0x5, tag.flag_mask=0x5, aggregate NV=1 |
| 16427.5 | Lane1 fflags_ex_valid_o=1, fflags_ex_o=0x10 |
| 16428.5 | MASKU accepts id=0, vm=0, vstart=0, VL=8; active-window=0xff, predicate low16=0; ALU valid/ready=0xf/0xf; predicate/old-vd valid=0xf/0xf; result queue full=0; in_ready_cnt_en=1 |

Only the low predicate bits within the active window are used as evidence:
unused upper predicate bits include X at acceptance, not coerced to zero by
the decoder. VMFPU publishes NV before MASKU accepts the architectural
predicate. This is direct evidence of missing architectural qualification,
not a conclusion inferred only from the final fflags mismatch.

## Active control: measured pass

`cycle_active01/{status.json,selected.vcd,cycles.json,cycles.csv}`.
Target PC `0x80000920`, same encoding. Same A/B, BE, queued vm and raw NV slot.
FP accept/return/flags/MASKU accept edges are 16543.5/16544.5/16545.5/16546.5.
At MASKU acceptance predicate low16=0x20, active-window=0xff, vm=0,
vstart=0, VL=8, all four operand valid/ready bits high, queue-full=0.
Expected/observed flags=16/16.

## Quiet control: measured pass

`cycle_quiet01/{status.json,selected.vcd,cycles.json,cycles.csv}`.
FP accept/return/flags/MASKU accept edges are 16499.5/16500.5/16501.5/16502.5.
Same queued vm=1, BE=0x33 and return mask=0x5. Raw NV slots are all zero;
published valid flags=0. MASKU predicate low16=0, active-window=0xff.
Both original sNaNs were replaced by qNaNs. This is an EQ quiet-NaN control,
not a no-NaN input. Expected/observed flags=0/0.

## Contract consequence

FP16 physical slot2 corresponds to lane1 byte offset4, the source byte for
sequential comparison element5. The existing compression loop in
`hardware/src/masku/masku_operands.sv` selects result bit0 from that byte.
Carrying NV at bit2 of the SAME result element maps this event to sequential
NV bit5. Qualification with accepted active-window and architectural
predicate would reject it in all-off and retain it in active_snan.
This mapping consequence is static; the proposed NV payload does not exist
in the captured baseline and is not claimed as tested here.

The capture does not establish stalled-slice behavior, multi-slice behavior,
or prefix-only localization. The original prestart case has a second sNaN
in tail element15; retain it and add an independently named pure-prefix
derivative. Do not reinterpret that original as a unique prefix proof.
