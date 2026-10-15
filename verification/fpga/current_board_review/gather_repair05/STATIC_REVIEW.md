# Gather Index-Origin Independent Static Review

2026-10-11. Read-only RTL review; no simulation or production edits. Confucius
owns the separate source/log/capture work. This report predicts the observed
failure but does not claim a measured cycle-level root cause or repaired PASS.

## Finding

**The proposed index-origin mismatch is structurally supported and predicts
the exact first reported79->0.** Current AluA skips complete index words using
lane-local architectural vstart, but VALU and MASKU still traverse the full
VL stream from logical element0. Operand queue does not restore the skipped
prefix. `scale_vl=0` means the skip does not shorten the request either.

Raw measured case: candidate04 launch02 ops20, e8m4, VL256, vstart128,
seed0/scalar0/mask mode0 (all predicate bits on), element128 expected79,
actual0. This is `vrgatherei16.vv v24,v8,v16,v0.t`, not scalar gather.
The cancelled ops1 sibling is not evidence of a second numerical failure.

## RTL Chain and Units

References are relative to repository root, at the reviewed hashes below.

1. `hardware/src/ara_dispatcher.sv:1204` defaults `scale_vl=0`; ei16 decode
   at1794 sets index EEW16 and source EMUL=next_lmul(m4)=m8 for SEW8. No
   ordinary ei16 decode rescaling override exists. `ara_sequencer.sv:796`
   forwards scale_vl. Source registers are v8-v11, indices v16-v23,
   destination v24-v27: the measured setup has no group overlap.
2. `hardware/src/lane/lane_sequencer.sv:428` makes lane VL=256/4=64;
   at448 localStart=128/4=32. AluA at951 carries localStart, no conversion,
   and at968 uses EEW16 with full VL64. The origin0 override at973 currently
   covers only `[VMSEQ:VMSBC]`, **not** VRGATHER/VRGATHEREI16.
3. `hardware/src/lane/operand_requester.sv:403` computes byte-based body
   length, but at416 selects original `vl=64` because scale_vl is false.
   Do not confuse the unused byte-length calculation with a compensating
   skip/shortened command. At423, address is
   `vaddr(v16) + (32 >> (EW64-EW16)) = base + 8 lane-local64-bit words`.
   For VLEN1024/NrLanes4 this is address72 rather than64, starting at v18.
   The command has EEW16, elem_count64, conversionNone. It requests16 words
   per lane, corresponding to original global indices128..383, not0..255.
4. `hardware/src/lane/operand_queue.sv:229` defaults conversion to the
   complete input word; at495 emits that word. No vstart field exists in
   this queue command. The select pointer is for conversion subdivisions,
   not architectural prefix compensation. None pops one whole word and
   counts four EEW16 elements per accepted lane word (510..537).
   An intra-word vstart is rounded down by the requester address formula;
   there is no arbitrary-element barrel shift here. This case is exactly
   word-aligned, so the omitted prefix is precisely128 global indices.
5. `hardware/src/lane/simd_alu.sv:152` passes operand_a for gather.
   `valu.sv:879` processes four ei16 elements per lane word despite SEW8;
   at1320 its issue counter is full localVL64. It does not prepend dummy
   words for localStart32. Each lane therefore supplies16 result words.
6. `hardware/src/masku/masku_operands.sv:107` deshuffles the ALU words using
   `eew_vs2`; dispatcher1795..1808 preserves the index layout for that path.
   This is a byte permutation within the current word, not a word-origin
   correction. Original `vle16.v v16` supplies the EEW16 layout.
7. `hardware/src/masku/masku.sv:1795` resets input/output/iteration counters,
   sets issue/processing count to full VL at1800, and sets gather scan0 at1914.
   ei16 selects16-bit indices at1379; input-word threshold is15 at1910,
   so one aggregate256-bit word covers16 indices. The scan runs0..255
   (1411..1428), regardless of architectural vstart.
8. MASKU result consumption also traverses0..255. `masku.sv:972` suppresses
   writes when `VL-issue_cnt < vstart`; it does **not** omit those input
   indices. `lane_sequencer.sv:1224` correctly starts the predicate stream
   at0 as well. Output merge/BE thus cannot correct shifted index data.

For this original source, expected indices include:

| MASKU logical position | Correct original index value | Current predicted source position/value |
| --- | ---: | --- |
| 0 | indices16[0]=0 | indices16[128]=511 |
| 128, first active destination | indices16[128]=511 | indices16[256]=513 |

`masku.sv:1347..1389` computes VLMAX512, **not VL256**, for the OOR check.
Correct511 is in range and `input[511]=79`; shifted513 is out of range.
The OOR result path at947..958 supplies zero without a MaskB source read,
which predicts the observed active element128 value0 exactly. Thus a
VL-versus-VLMAX clamp is not the leading static explanation in this RTL.
This remains a falsifiable prediction until the issued request and consumed
index are captured for the actual target instruction.

## Minimal Proposed Edit Scope, Not Implemented

In the existing non-mask-source AluA branch only, expand its origin0 test to:

```systemverilog
if (pe_req.op inside {[VMSEQ:VMSBC], VRGATHER, VRGATHEREI16})
  operand_request[AluA].vstart = '0;
```

Keep the architectural VFU/MASKU vstart, VL, EEW, scale_vl, masks, hazards,
snapshot metadata, destination BE and ad-hoc MaskB indexing unchanged.
Do not globally zero all MaskUnit requests or restart MASKU counters at vstart.

| Operation | Applicability and boundary |
| --- | --- |
| ordinary `vrgather.vv` | Same AluA bug class when vstart crosses a complete index word. EEW follows the ordinary index-source contract; restore origin0. Not yet a measured second failing case. |
| `vrgatherei16.vv` | Measured case; index EEW16 independent of data SEW. Full original index stream must start0, including EMUL8 for this e8m4 shape. |
| `vrgather.vx` / `.vi` | Same enum VRGATHER but dispatcher2049/2298 leaves use_vs1=false and uses scalar_op. AluA push at987 is false; the proposed field change causes no operand request. MASKU1383 overrides the index with full scalar/overflow qualification. Keep accepted scalar OOR/end-token behavior. |
| `vcompress.vm` | Packed-bit AluA branch (980), different scan/output count and sentinel contract. Not in proposed set. Dispatcher157/5276 requires vstart0; legal operation already starts0. Do not broaden to `[VRGATHER:VCOMPRESS]`. |
| integer compares and carry/borrow `[VMSEQ:VMSBC]` | Already origin0 here; retain unchanged. Do not alter AluB, mask routing or result compression. |
| FP compares `[VMFEQ:VMFGE]` | Separate MulFPU operand requests, already origin0. No producer NV/flags or predicate changes. |

Source/source-alias snapshot replay deserves later representative regression,
not a new snapshot design: requester445 derives replay word index from the
same request vstart. Origin0 must mean snapshot word0 too. This actual
disjoint case does not establish alias acceptance. Legal high source groups,
different SEW/ei16 EMUL, and partial final index words retain existing sizing;
do not set scale_vl=1 to compensate, because data SEW and index EEW differ.

## Tail and Terminal Token Safety

- Keep full `ceil(VL/NrLanes)` index count and VALU EI16 word width. MASKU
  scans exactly VL positions and releases the last partially consumed index
  word at `scan==VL-1`; it must not scan the padded slots or stop at VL-vstart.
- In-range final index enqueues its normal source request with is_last_req.
  OOR final index still enqueues an index token and a separate request token
  `no_data=1,is_last_req=1` (`masku.sv:1392..1403,1424..1428`). Earlier OOR
  entries produce zero but no data request. Do not remove the final token
  merely because an entry is masked/prestart/OOR.
- `lane_sequencer.sv:258..273` accepts no_data without allocating MaskB or
  incrementing its command count, and returns REQUESTING to IDLE on accepted
  last token. `1245..1261` pushes MaskB only for data requests; its vstart is
  **the fetched source index divided by lanes**, not architectural vstart.
  It must not be zeroed by this fix.
- Per-lane request acceptance bookkeeping `masku.sv:623..639`, index FIFO
  ordering, final source-response draining and result-write completion stay
  unchanged. Changing index origin changes which entries are OOR, so count
  actual in-range requests, not a hard-coded old request total.
- VCOMPRESS final-zero-mask dual sentinel (`masku.sv:1331..1339`) and partial
  output flush are independent and must remain unchanged. VL0/no-op and
  next-instruction cleanup need control acceptance, not an invented extra
  terminal token for an operation that was never issued.

## Focused Probe Contract

Use one real target identity and match its instruction/ID at every stage;
do not correlate unrelated queued instructions by time alone. No capture
script or simulation was created/run by this review.

| Stage | Required observations and discriminating expectation |
| --- | --- |
| Dispatch/lane acceptance | op, vs1=v16, vs2=v8, vd=v24, VL256, start128, SEW8/LMUL4, index EEW16, use_vs1, scale_vl0, snapshot replay flag; lane AluA valid/ready/push, vl64/start32 before, start0 after proposed edit. |
| Actual VRF read | AluA `requester_metadata_q` id/addr/len/vew, bank request/grant and returned word. Before first address72, not64; no advance on mere valid without grant. Snapshot replay should be false for this disjoint case. |
| Queue and VALU | AluA command elem_count64/eew16/convNone, input/output data valid/ready; VALU id/issue_cnt/operand_a/result and result ready to MASKU. Tie first accepted aggregate word to original indices128..143 before,0..15 after. |
| MASKU index acceptance | vinsn_issue id/op/eew fields, `vrgat_cnt_q`, `in_ready_cnt_q`, `masku_operand_alu_seq`, all lane valids/readies, `vrgat_idx_fifo_push`, `vrgat_req_idx_d`, `vrgat_idx_oor_d`, request FIFO push/no_data/is_last. At accepted scan128 predict513/OOR before versus511/in-range after. |
| Result acceptance | Do not assume scan and result stages are simultaneous. At index FIFO pop for logical result128 (`VL-issue_cnt=128`), inspect head index/OOR, predicate bit128, fetched operand valid/data/ready, queue-full, BE and result data/addr. Before zero from OOR; correct fetched seq byte31 is79 for source511, with nonzero active BE. |
| Completion | Scan255 last token, every lane valid/ready acceptance, request FSM IDLE, final source response and result write grants, empty/retired queue state, architectural vstart0; successor op can complete with no leftover index/mask/source tokens. |

Correct source511 request has local idx127, data EEW8, and source VRF
`vaddr(v8)+15` (47 in this configuration). If scan128 instead measures511
with OORfalse already, this hypothesis is falsified for that target: inspect
MaskB source payload/layout and result BE/merge rather than changing AluA.

## Original Source and Minimum Faithful Reproducer

Base directory: `../gather_original_review/stall_prefix2_03/`.
Archived child `rvv_permute_restart_e8_m4_ops20`:

- Original Linux ELF SHA256:
  `15469ee7ca24fd7a7dac6e282358872a5d9c3dfc836e5de363661925fac70c18`.
- Retained original C SHA256:
  `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`.
- Actual launch02 private SoC ELF SHA256:
  `be97b7369ae580019755ac4c5d6e331677050d110943e777142441594490c7f2`.
- Launch02 plan SHA256:
  `64fa59ee5ff9533268bfe8e33165a5979695c4009135cf3b0c3d6db93ad48c45`.
- Exact source row: `gather_prefix_e8_m4_ops20.host_expected.json`, ordinal66
  (row65), tuple `[0,20,0,4,0,1]`; original C loops at scenario.c:57..95.

Minimum proposed source-preserving single retains seed0 xorshift RNG
initial0xe736815b449aec21, all512 source bytes and512 uint16 indices,
all-on mask, entire514-byte output allocation initialized0x5b, original
`op_20` assembly at `prepared/gather_prefix_e8_m4_ops20/original/operations.S:308`.
That assembly loads full capacity under e8m4 (`vle16` index EMUL8), loads
old vd and v0, selects VL256, writes vstart128, executes the unchanged target,
reads vstart, then stores full capacity. Check all512 outputs, both guards,
and returned vstart, not just element128. Expected prestart/tail remain0x5b.

The single would explicitly omit previous vector history. For historical
sequence coverage retain original prefix through ordinal66, or next retain
the immediate ordinal65(start1)->66(start128) pair with original reloading
and oracle. Neither is the whole98 prefix or proof of the unknown final
trial in the11 archived stalled records. Do not alter the existing98-prefix
ELF/pins. Confucius owns implementation/capture decisions; no new case was
prepared here. Scalar/vv controls and final-OOR/in-range tails should reuse
accepted original source points, not expand into an unrelated matrix.

## Reviewed RTL Identity

All eight current files below were freshly hashed and matched candidate04
`/home/wangwy/fpga_runs/current_board_memory_candidate04/frozen/sources/`
byte-for-byte and their `snapshot.json` pins. This is not merely a review
of a newer worktree than the failing image. Image.json SHA256 is
`e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.

| File under hardware/src | SHA256 |
| --- | --- |
| lane/lane_sequencer.sv | `dfda48c8f3c9c1a1f0f41499a48b890cfaa112eb822f702ed8738fe3ae3705fa` |
| lane/operand_requester.sv | `327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2` |
| lane/operand_queue.sv | `eafc82bfe3bd7413aa549015a2145e977d1ce01a9bd52c369993e5dac10e453d` |
| lane/valu.sv | `f8a8cd12e9d4732eca87e1c9a1aa48b52a8e684f2d7e64d0e8ec1faa9411c778` |
| lane/simd_alu.sv | `8d84858bd3dbb3baab5e2b12b8eb0c36cceb407373adee9dc0285ab8dfa962bc` |
| masku/masku.sv | `1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d` |
| masku/masku_operands.sv | `c907488c75b5051a917e61c5ac08bca15859f2f0506fd61dae07dd576569456f` |
| ara_dispatcher.sv | `05e9a4633d3d3a989fc5433fbf647c26c9d21ec1837b210ee84b6c712f6815fd` |
