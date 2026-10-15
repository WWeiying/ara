# Original FP e16/m8 Versus Current M6 Logic

Static review, 2026-10-12. **Original call50 remains unresolved, not a proven
current-M6 defect and not closed by the flags/restart fixes.** No execution,
reference reparse, build, live query, or RTL/test/helper edit was performed.
The authentic682 prefix stays HOLD under the user's three-hour limit.

## Exact Historical Evidence

Archive root A:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
The actual `A/rvv_compare_uncovered01/original_board_report.json`, SHA256
`7ed11ee7257c8571d8d5d4bf87780231d82fd5373173343598d21d47ed5aa00f`,
contains the following in the SAME failed parent result, exit1, 19.64310640003532s:

| Retained symptom | Exact fields | What the original oracle establishes |
| --- | --- | --- |
| Call50, data-dominant | op0, seed0, VL512, mask mode0, sticky1, expected_flags17, actual_flags17, errors64 | Unmasked `vmfeq.vv v8,v8,v16`, start0, all512 bits active. Between62 and64 result-bit errors: vstart and combined guards contribute at most two more. Not evidence of64 specific bit positions. |
| Calls681/682 and later short-VL contexts | op2, seed1, VL1, mode0, sticky0/1, expected0/1, actual16/17, errors1 each | Unmasked `vmflt.vv v8,v8,v16`; the flag mismatch consumes the sole error. Other checked data, vstart and guards pass on those calls. |
| Other retained details | op2/seed1, all four modes at VL1/2, then VL3 mode0 sticky0/1 and mode1 sticky0 | Same excess NV. Only20 details are retained, not the complete set of failing tuples. |
| Full parent summary | cases17920, errors1252 | Neither1252 independent bugs nor a complete location map. |

The later recovery08_11/terminal_scene and recovery08_12/previous_report
records instead retain errors1472 and omit the64-error detail. They contain
the same later output, not two independent reruns. Do not substitute that
record for the1252-error report or infer a reproduced call50 from it.

Parent ELF:
`A/rvv_additions45/binaries/rvv_fp_compare_unmasked_alias_v8_e16_m8`,
SHA256 `266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754`.
Original assembly identity:
`eb5659c77622636492675c2ffd77b2e1a2fc93ede9471013d123f54151a02f86`.
Recovered original C in `provenance01/fp_compare_oracle_3652.c`:
`3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c`.
The existing source proof rebuilds this full original Linux ELF byte-identically
before adaptation. The archived uncovered single explicitly labels its oracle
`current_reconstruction`; that provenance is not silently upgraded.

The source uses no mutable RNG: lhs index `(i+seed+7*(seed/16))%16`, rhs vv
index `(3*i+5*seed+seed/16)%16`. Each helper reloads both full-capacity inputs,
loads v0, sets target VL and sticky flags, executes the original comparison,
reads vstart/flags, restores saved flags, and stores the capacity-sized mask.
These vv helpers have16 instructions, not the13-instruction gather contract.
See `prepared02/prepared/alias_v8_e16m8_prefix682/case.c:40` (loop order),
`:47` (initialization), `:58` (call), and `:59` through`:84` (original oracle).
Compile-time settings are unmasked1, restart0, destination-kind1 (v8).
Loaded mask mode3 therefore does NOT make this target all-off.

At call50 the expected64 result bytes are all `01`. An all-zero result could
produce64 bit errors, but the archive does not print actual bytes; that is a
discriminator, not a reconstruction of the observed output. No tail-agnostic
permission can excuse a bit mismatch here: all512 checked bits are active.

The archived50-call diagnostic prefix passed with all64 bytes `01`, flags17,
vstart0 and guards91/91 (`ready_audit01/existing_prefix50.json`, binding
`A/rvv_compare_prefix_board232_01.json`, SHA256
`cc3e73e27180c8271b861d7afe0059f6ea10c436bed0c37baad20e49cd25682b`).
The isolated child also passed historically. Removing diagnostic printing
and the stop from the old prefix recovers the reconstructed C; the recovered
historical C rebuilds the same parent ELF. Thus a simple C-oracle version
disagreement is not supported. Logging/code layout, runtime and Linux history
remain different; neither intermittency nor a specific hardware cause follows.

## M6 Identity And Relevant Paths

Frozen image ledger:
`/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image/image.json`,
SHA256 `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
The following current files were rehashed and byte-compared equal to M6's
`frozen/sources/hardware/src/` files. Line references below are current/M6 alike.

| File under hardware/src | SHA256 |
| --- | --- |
| lane/lane_sequencer.sv | c11e2a871b91a7aaf940f9e4fb0ef79229a48a2a9b7e2db3fd1108e24dc01dcc |
| lane/vmfpu.sv | e9b8c8c2aa952b76661b01fa0a4b53d87e2f1d7219beb40a42a4d6998c5f7b12 |
| masku/masku_operands.sv | c907488c75b5051a917e61c5ac08bca15859f2f0506fd61dae07dd576569456f |
| masku/masku.sv | 1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d |
| ara_dispatcher.sv | c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d |
| ara_sequencer.sv | bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655 |
| ara.sv | 1d190744249603d6c3d6e2c9c21cd5ac121fee2a9c65f5b227be239c320286da |

1. `ara_dispatcher.sv:3473` decodes vv comparisons with source EEW=CSR SEW,
   old-vd EEW and stored-result `vtype.vsew` from vd metadata. `:5285` permits
   the exact source-base mask-result alias used here. `:5950` updates written
   register layout metadata. Correct execution must preserve the distinction
   between source elements and packed-mask output layout, not force all to EW8.
2. `lane_sequencer.sv:409` restores comparison execution SEW from source EEW;
   `:430` balances local VL across lanes. `:1027` and`:1053` feed MulFPUA/B
   from origin0, with source EEW and source/old-vd dependencies. `:1076` through
   `:1109` fetch old packed destination words through MaskB from origin0.
3. `vmfpu.sv:1225` classifies per-element NV: EQ/NE only sNaN, LT/LE any NaN.
   `:1253` carries dense NV in the FP tag; `:1542` packs comparison bit0 and
   NV bit2; `:1585` suppresses unqualified lane comparison fflags. `:2740`
   keeps queued comparison vm=1 intentionally: MASKU owns the real predicate.
4. `masku_operands.sv:227` compresses bit0 and bit2 with the SAME source-EEW
   shuffle and `vrf_pnt`; NV outside that slice defaults0. `masku.sv:448`
   publishes flags only on accepted comparison slices, qualified by the
   exact active window (`:795`) and predicate OR architectural vm.
5. `masku.sv:1010`,`:1018`,`:1036` preserve outside-window bits and shuffle
   result/background using stored-output `vtype.vsew`. At unmasked VL512,
   every bit of both packed output words is active, so old-vd/predicate data
   must not suppress active comparison bits. `:1459` protects queued
   descriptors while full; `:1479` gates slice acceptance; `:1607` resets
   the packing pointer after publishing each output word.

## Which Fix Can Explain Which Symptom?

**Short-VL NV: strong mechanism match, not exact-parent M6 acceptance.**
For seed1, the original FP16 source pairs at i0..3 are respectively
`8000/4000`, `3c00/0001`, `bc00/7bff`, `3800/7e55`.
The first three are finite; i3 contains qNaN in rhs. Balanced local VL1 at
global VL1/2/3 can compute that lane3 comparison although i3 is architectural
tail. Ordered LT raises raw NV on qNaN. The present bit2/window contract
excludes i3 for all three VLs. This directly predicts sticky0/1, not16/17.
It is a concrete candidate contributor, not a measured raw lane3 event from
the historical run. Other out-of-window physical slots must also be excluded.

The missing-qualification mechanism is independently measured in
`../comparison/cycle_proof.md`: raw lane1 NV16426.5ns, unqualified lane flags
16427.5ns, all-off MASKU acceptance16428.5ns. The selected baseline had data
PASS/flagsFAIL. Current producer/consumer and integrated comparison regressions
exercise the repaired contract, but not this original682-call history.

**Restart origin: measured fix, not an explanation of call50.**
`../comparison_source_controls/AB_REPORT.md` preserves same-ELF M3 vv/vf
start16 errors10 -> M4 PASS, and byte-identical zero-start control CSVs.
`TERMINAL08.md` independently accepts the two authentic e16/m2 130-call
restart prefixes on M4 (260 calls, not this m8 parent).
`../comparison_source_controls/nv_successor/DUT_REPORT.md` has8 M4 controls
with exact NV for prestart/inactive/active sNaN and EQ/NE versus LT qNaN.
Call50 and calls681/682 have start0; zeroing source/MaskB origins does not
change their starting address. These PASS results cannot close their data gap.

**Full-queue descriptor overwrite: measured repair, plausible historical
data mechanism only.** `../comparison/test_matrix.md` records real MASKU
before04 cycle47 full1/wp=rp0/iteration2/noaccept/no-grant, entry0 addr q96/d98;
after05 retains96 and writes96/97, with all24 consumer cases passing on the
same MASKU SHA now in M6. Original VL512 produces32 accepted16-element slices
and two256-bit output words (four lanes, FP16); it can exercise this two-entry
queue boundary. There is no archived call50 queue waveform proving fullness
or wrong address. Do not attribute its64 errors to this fix without that link.

**Source alias/layout/dependency: unresolved candidates, not demonstrated bugs.**
Normal in-instruction self-overwrite is not established merely by vd=vs2:
the first packed word is published only after256 source elements are consumed
(`masku.sv:1846`,`:1564`). Physical v8 contains only64 FP16 elements, already
consumed before its first32 result bytes are written. Wrong/stale source data
from older loads, wrong stream ordinal, or packed-result metadata/readback
still require observation. `ara_sequencer.sv:610` through`:700` tracks RAW,
WAR/WAW groups; `lane/operand_requester.sv:496` gates reads using the recorded
hazards/progress. No missing dependency for this exact history was proven by
this review. M6's indexed-load snapshot/dedup repair is not a compare repair.

M6 regression48's terminal audit in
`../gather_repair05/m6_regression48_terminal_audit01/REPORT.md` accepts its
exact48 programs and16 byte-identical control traces. This is current-image
regression evidence, not execution of this held prefix or all17920 calls.

## Discriminating Signals If Separately Authorized

Keep the original682 source/ELF/oracle/history frozen. No shortened execution
is proposed as closure. A later capture must trigger on actual helper/call
identity, not a guessed absolute time; select a bounded window from the two
source loads through mask store and CSR reads. Prepared target PCs are
op0 `0x80000508` and op2 `0x80000580` (bind against the actual executed ELF).

| Boundary | Minimal fields | Falsifiable distinction |
| --- | --- | --- |
| Decode/issue | accepted ara_req/pe_req id, op, vm, VL, vstart, vs1/2/vd, source/old-vd EEWs, vtype.vsew, eew_q[8..23] | Wrong request/layout versus correct request followed by downstream corruption. |
| Source delivery | MulFPUA/B and MaskB request valid/ready, addr/EEW/VL/start, hazard/wait-complete, actual VRF grant/data; preceding load id/write addr/data/BE; operand queue pop | Compare actual source words against the original arrays and consumed ordinal; prove any read-before-write or advanced/stale word rather than assuming it. |
| VMFPU | vinsn_issue_q, operand_a/b, issue_be, FP input/output valid/ready, operation/format, result, raw status, tag in/out; published lane flags | Correct operands but wrong bit0 identifies arithmetic/comparator path; correct bit0 but later failure does not. For short VL, locate i3 qNaN NV and track its bit2. |
| MASKU accept | vinsn_issue, all ALU/old-vd valid/ready, compressed bit0, fp_compare_nv_seq, active mask, predicate low relevant bits, vrf_pnt, iteration, issue/out counters | Exact stream ordinal, active qualification, and one acceptance per slice; ignore unused X predicate bits when vm1. |
| Write/store | queue count/full/read/write pointers, entry q/d addr/data/BE/id, masku_result_req/gnt/final_gnt, shuffle EEW; subsequent vsm read/grant/data and memory bytes | Correct compressed bits but bad queued word/address versus correct VRF write and wrong stored layout/readback. Hold entries stable through stalls and count both words once. |
| Architectural endpoint | exact helper target/CSR/store PCs, returned vstart, fflags before/after, full64 result bytes and both guards | Localize the aggregate64 errors; distinguish all-zero output, sparse wrong bits, store/guard failure, or an unrelated instruction. |

Observe the same accepted instruction id across stages; distinguish output
request from grant and final grant. Fflags validity is a pulse on accepted
slices, not evidence of VRF completion. A static bit-count match is not proof.

## Disposition

No new proven comparator bug and no basis for another RTL patch were found.
The retained exact data failure remains open; existing fixes plausibly cover
the distinct flags symptom and demonstrably cover separate restart cases.
Only20 original details exist here, so no conclusion covers all1252 errors.

`fp682_cost_feasibility01.md` retains the measured-reference20260288 retired
instructions and estimate8.02..8.08h from actual130-prefix throughput. Required
initialization/full-capacity oracle dominate; no empty post-target enumeration
was found. This is not an M6 measured duration or a guarantee. No launch,
budget escalation, history reduction, or historical/Linux closure is authorized
or claimed by this report.
