# Original Min Follow-Up Scope

Static only; no new compilation, reference or DUT dispatch.
Original source loop order:
row=scenario*420 + length_index*60 + mode*15 + frm*3 + op;
zero-based call=2*row+sticky.

| Original call | Scenario/length/VL | Mask | frm/op/sticky | Bank1 row | Archived result/flags |
| --- | --- | --- | --- | --- | --- |
| 1292 | 1/3/3 | mode3,0x24 | 0/1/0 | 646 | 7fc00000/0 |
| 1232 | 1/3/3 | mode1,0 | 0/1/0 | 616 | 7fc12345/0 |

Both authentic fixtures were read from archived e32/m1/fixtures.json, SHA
59bd5276e2306391784b16263818f725424392421bebc355b1db6c25cbebd53a.
All source and seed words come from archived input_bits[14]=7fc12345.
1292 only activates source element2;1232 is alloff at nonzeroVL.
The original op1 helper is21 instructions with the same setup/context/store
policy as op2, replacing only the arithmetic opcode with14881c57/vfredmin.
Existing reviewed e32/m1 SoC single selects scenario3/VL16/op0; reviewed
remaining9/e16-mf4 singles also select op0. No current M6 SoC acceptance of
these exact two min tuples was found in the inspected evidence.
Matrix84 min tests are module-level and not these original tuples.

Applicability: prepare two further source singles, each retaining original
input/fixture traversal,21 helper and full144B result/flags/vstart/context
oracle. Neither max single substitutes for min acceptance. No original
full-Linux/parent claim, no preceding1292-helper prefix.

Cost planning: same scalar loop/setup counts and21-instruction helper as
the compiled max singles. Their proven normal-path envelope is2,143,584
instructions. This is a planning envelope for min, not a compiled min
admission or measured cost. Recheck actual compiled selector/CFG/helper
encodings in a new successor before any reference. Proposed independent
bounds remain3M steps/120s/256MiB per raw file, once per case, first-error stop.
No sealed consumed helper/adapter is to be edited.
