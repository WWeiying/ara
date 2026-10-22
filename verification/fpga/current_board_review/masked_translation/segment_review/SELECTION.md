# Archived NF2 Selection

Status: source/archive audit only. No build, simulation, new ELF, or production
change. Static path review is in `../SEGMENT_REVIEW.md`.

## Exact Source Identity

Archive root H:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_segment_fault_handoff01`

Selected existing source directory T, relative to H:
`controls/rvv_trace_fault_replay_segment_nf2_e16_m1/`

| File relative to T | SHA256 |
| --- | --- |
| case.json | 1e5398466514e77fb89ac4d4b919c709e76e28329f683996c9697cad5e6404b0 |
| baseline.c | 631da853fe5939e2a812145d23155767d4e803f3d9aa22133187d6455905588a |
| scenario.c | 0209ece14754d4df401014bcb0d17b2f94d497f8c10e17d43c0ab93191521aaf |
| scenario.S | de5487a9ec451569e10485d8e2a78e458b7c519e417aee31bffded645569a7ac |
| scenario.elf | a1879ca34838deeac86a3f5050c7be8d2508633c288bb5bc5258b365389e14a8 |

Original identity: `rvv_fault_replay_segment_nf2_e16_m1`.
Original retained ELF:
`H/controls/rvv_trace_fault_original_segment_nf2_e16_m1/scenario.elf`.
SHA256: `3fb155679a00980cc07e34a858e7eea84c1c390e6af054f8f868ee03ba6c7054`.
Its `case.json` SHA256 is
`160edb929ac0c94840da547c32798655e291eeb113b6e3c4342b9fcf74afa4d4`.
The retained rebuilt baseline ELF at
`H/controls/rvv_trace_fault_baseline_segment_nf2_e16_m1/scenario.elf`
has the identical original ELF hash. This audit verified retained identities;
it did not rebuild. T/scenario.c adds trace diagnostics to T/baseline.c;
the trial loops, inputs and oracle are retained.

## Selected Tuple And Evidence

Primary load: `unmapped=0, store=0, boundary=5, mode=2, split=1`.
Companion store: same tuple with `store=1`. These are zero-based full-sequence
trial indices 21 and 45, respectively. Both use NF2, e16m1, VL8, tu/mu,
vtype=8, v24/v25, and repeating mask byte 0x24 (active elements 2 and 5).
Initial vstart is zero; the fault/retry vstart is **5**.

These are genuine trials in the original full-sequence source, but the archived
instrumented run reports **errors=0 for both**. They are positive fault/restart
controls, not members of the 40 exported failing singles. There is no exported
`b5_m2_f1` standalone ELF. A focused Sv39 port must be called a selected-trial
semantic derivative, not the full original Linux reproducer.

Evidence: `H/evidence/controls_board_report.json`, `results[2].output`:

```text
RVV_FAULT_BEGIN unmapped=0 store=0 boundary=5 mode=2 split=1
RVV_FAULT_CONTEXT sig=11 code=2 address=273693114368 expected_address=273693114366 pc=68394 expected_pc=68394 vstart=5 expected_start=5 vl=8 vtype=8
RVV_FAULT_RETURN status=0 faults=1 expected_faults=1 handler_errors=0
RVV_FAULT_CHECK errors=0
```

The store trial has the same context except pc/expected_pc=68456, also one
fault, status=0, handler_errors=0, errors=0. Full-program original/baseline/trace
aggregate failure is `cases=96 signals=96 errors=64`; do not attribute that
aggregate failure to these passing trials.

Evidence file SHA256:
`6d4a5c4c65961db387d3bb580ba3c8cd8491b8e2d38f7180fbfb8ef2f506b52b`.
`H/evidence/control_symptoms.json` SHA256:
`70675b3978084fb900f7ee8a63455fafbb3c8c21ca906a5e0b99b6ffd5b989f4`.
All 180 entries of H/hashes.json were checked without mismatch during this audit.

Instruction identities from retained ELF disassembly:

| ELF | Setup PC | Fault PC / opcode | Next PC / opcode |
| --- | --- | --- | --- |
| Original load | 0x109a4: c08472d7 | 0x109a8: 20055c07 | 0x109ac: 00802573 |
| Original store | 0x109e2: c08472d7 | 0x109e6: 20055c27 | 0x109ea: 00802573 |
| Trace load | 0x10b26: c08472d7 | 0x10b2a: 20055c07 | 0x10b2e: 00802573 |
| Trace store | 0x10b64: c08472d7 | 0x10b68: 20055c27 | 0x10b6c: 00802573 |

Setup is `vsetivli t0,8,e16,m1,tu,mu`; fault instructions are
`vlseg2e16.v v24,(a0),v0.t` / `vsseg2e16.v v24,(a0),v0.t`;
next instruction reads vstart. Source labels are fault_0_pc/fault_1_pc.

## Geometry, Inputs And Independent Oracle

Let M be the 8192-byte mapping base and P=M+4096. Both pages are initialized;
Linux mprotect makes the second page PROT_NONE (`unmapped=0`).
Target=P-22=M+4074; field address A(i,f)=target+4*i+2*f.

| Element | Predicate | field0 | field1 |
| --- | --- | --- | --- |
| 0,1 | inactive | accessible | accessible |
| 2 | active, completed prefix | P-14 | P-12 |
| 3,4 | inactive | accessible | accessible |
| 5 | active, fault/restart | P-2, accessible | P, protected |
| 6,7 | inactive | protected | protected |

Archived M=0x3fb9617000, P=0x3fb9618000, target=0x3fb9617fea.
Printed expected_address=P-2 is the segment base, **not** the failing field.
The C oracle requires an address within that segment AND the protected page;
only P is admissible here. The printed two-byte difference is not an error.

At VLEN1024, cap=64 halfwords per field, field registers v24 and v25.
Preserve these exact formulas (uint16_t arithmetic):

```text
memory[address] = ((address-M)/2)*37 + 11
input[f*64+i] = 101 + 13*i + 29*f
mask[0..15] = 0x24
initial load v24/v25 = 0x005b, all 64 elements each
initial store v24/v25 = input, all 64 elements each
output data begins at output+1; guards output[0], output[129] = 0x005b
```

Original load values: element2 fields=(0x2708,0x272d), element5
fields=(0x27e6,0x280b). Store input values: element2=(127,156),
element5=(166,195).

Oracle from baseline.c:143-173 and :257-274:

1. Exactly one SIGSEGV/SEGV_ACCERR, correct fault PC, VL8/vtype8/vstart5;
   terminal vstart/status zero. Inspect saved register prefix i<5 in both
   fields: active load element2 has original values, inactive prefix is 0x5b;
   store registers retain input and completed active prefix memory has input.
2. The original pre-repair oracle does **not** constrain faulting segment i5.
   In particular, v24[5] may already contain field0 data when field1 faults.
   Do not add an all-fields-untouched requirement for this segment.
3. Restore page permission. Poison ONLY completed active prefix element2 in
   both fields: memory XOR 0x5b for load; input XOR 0x5b for store. Preserve
   saved PC, vstart and vector registers; retry the same instruction at vstart5.
4. Final load registers: active elements2/5 retain original memory values;
   all other elements, including tail8..63, remain 0x005b. Final store source
   registers retain all original input values.
5. Check the entire 8192-byte memory: load changes only poisoned prefix;
   store leaves prefix poison, writes element5 input, leaves everything else
   original. Check both output guards. This detects erroneous replay from0.

## Adjacent Archived Failure, Kept Distinct

Existing standalone directory relative to H:
`singles/rvv_small_fault_segment_nf2_e16_m1_u0_s0_b3_m2_f1/`.

| File | SHA256 |
| --- | --- |
| case.json | 558c4f6b5c043ed6ad66c46dbcfdd1177df3a9dfc2d6cd711d2d8128bd6db0ae |
| scenario.c | 456be478583f008e81ce0bb4b616aa732826847bbdf6be6dfe3895ac49f7ddb9 |
| scenario.S | de5487a9ec451569e10485d8e2a78e458b7c519e417aee31bffded645569a7ac |
| scenario.elf | 4a65fbeeb124493187e56aca1ca28504497139b7b243cff257e864640b6adaf5 |

Role is `single_current_oracle_trial`, not byte-identical original. Tuple differs
only in boundary=3: target=P-14. Segment3 is inactive and straddles the page;
first active protected segment is5 (fields P+6/P+8). Archived hardware faulted
early at P with vstart3 instead of5, handler_errors=1/errors=1. This is the
more discriminating historical suppression failure, but its active fault
segment does not itself straddle the page. Keep both geometries explicit.
In names, s0/s1 means load/store selection, not initial vstart.
