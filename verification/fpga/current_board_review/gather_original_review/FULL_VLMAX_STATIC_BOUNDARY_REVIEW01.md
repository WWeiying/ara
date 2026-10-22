# Frozen M6 e8/m8 Full-VLMAX Static Boundary Review

2026-10-11. **Preparatory static review, not new DUT/reference PASS, liveness proof, or global type proof.** No RTL/helper edit, DUT/Host/reference/build, process/service query or active e8/VI observation. Only this new note is written.

## Verdict and Identity

No concrete **1024-global /256-per-lane representation or final-BE correctness defect** was found in the inspected frozen M6 path. The narrow counters are word-local indices or queue occupancy, not global VL. Mask-off does not suppress the gather scan/source stream or completion transactions. Full-VLMAX behavior remains unmeasured in the proposed112 scope; do not infer it from passing66 or from widths alone.

One concrete internal arithmetic observation is retained: VL1023's last `processing_cnt` subtract wraps31-32 to2047. It is **not demonstrated as an architectural bug**: the current descriptor uses old31, issue/commit counters terminate separately, and a new context reinitializes processing. Its exact conditions and distinguishing probes are below; it must not be misreported as a stuck remaining-element count.

Frozen root `F=/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen`; RTL root `S=F/sources/hardware`.

- Actual `F/snapshot.json` SHA `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`; settings explicitly `nr_lanes=4`, `vlen=1024`, `mc=0`.
- Actual image ledger SHA `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`, configuration SHA `6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785`.
- All16 inspected frozen files were freshly hashed against their `snapshot.json` entries: ara, dispatcher, sequencer, ara/rvv packages, masku/operands, lane/sequencer/VALU/SIMD ALU/operand queue/requester/regfile, common `idx_width`/delta counter. This is source identity checking, not a fresh simulation-image/build validation.
- Key source hashes: MASKU `1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d`; lane sequencer `c11e2a871b91a7aaf940f9e4fb0ef79229a48a2a9b7e2db3fd1108e24dc01dcc`; VALU `f8a8cd12e9d4732eca87e1c9a1aa48b52a8e684f2d7e64d0e8ec1faa9411c778`; operand requester `327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2`; operand queue `eafc82bfe3bd7413aa549015a2145e977d1ce01a9bd52c369993e5dac10e453d`.

## Units and Widths

ELEN/DataWidth=64bits, ELENB/StrbWidth=8bytes. VLEN=1024bits **per architectural register**, not1024bytes. e8/m8 VLMAX=(1024/8)*8=1024elements/bytes. Four lanes carry256bytes/elements each; an aggregate data beat is4*64bits=32bytes/elements, while an aggregate packed-mask beat is256 **bits/elements**.

Primary declarations: [ara.sv:46](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/ara.sv:46), [lane.sv:137](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/lane/lane.sv:137), [masku.sv:64](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/masku/masku.sv:64), [MASKU counters:435](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/masku/masku.sv:435), [cf_math_pkg:57](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/deps/common_cells/src/cf_math_pkg.sv:57).

| Quantity | Actual width / representable range | Unit and required boundary |
| --- | --- | --- |
| `vlen_t`, CSR VL/vstart, pe/vfu `vl/vstart` | `$clog2(1024+1)=11`, unsigned0..2047 | Global elements at MASKU/dispatcher; lane elements in vfu/request metadata. Both1024 and256 fit. |
| MASKU `issue/read/processing/commit_cnt`, `vrgat_cnt` |11,0..2047 | Issue/commit are global remaining elements; scan is absolute destination index0..1023, not a source address. `read_cnt` is not the gather ALU's completion counter. |
| VALU `issue/commit_cnt`, requester metadata `len`, queue `elem_count`, command `elem_count` |11,0..2047 | Per-lane data elements256, or packed-mask **64bit words4**. Queue cumulative data consumption8..256 fits. |
| `in_ready_cnt`, `in_m_ready_cnt`, `out_valid_cnt` | `idx_width(4*64)=8`,0..255 | Word-local slice positions. e8 gather thresholds31/255/31 respectively; clear per data/mask/output word. They never have to hold1024. |
| `mask_pnt`, `vrf_pnt`, `delta_elm` | `[idx_width(256):0]`=9,0..511 | Aggregate-word-local bits; gather delta1, output pointer resets each published32-element word. Mask-queue pointer is not gather's mask scan counter. |
| `iteration_cnt` | `MAX_NUM_VRF_WORDS=1024/4/8=32`; index5bits0..31 | Aggregate output-word address offset. All32 words use offsets0..31; increment after last may wrap0, not needed as address32. |
| `elm_per_lane`, `be(cnt,EW8)` argument |4bits0..15; locally clamped to8 (plus optional remainder1) | Elements in **one lane word**, not lane total256. Full quotient comparison clamps before it is used; 256 truncated to0 is not the final value. `be(8)`/`be(9)` enables all8bytes. |
| `strb_t`, `be_vrgat_seq` |8bits/lane,32bits aggregate | Per-byte enables, not element totals. |
| `max_vlen_t`, request index / FIFO source index |16bits0..65535 (`RISCV_MAX_VLEN=65536`) | Global source element; request divides by4 to lane-local index. Scalar1023 would become255, representable. Scalar1024 is OOR before issuing a data request. |
| `vaddr_t` | `idx_width((128/4)*32)=10`,0..1023 | Declaration sized from bytes, used here as lane64bit-word address. Actual VRF128 words/lane; vd24 base96 through vd31 last word127 all fit. Bank index3bits, SRAM row4bits. |
| Result queue occupancy / pointers, req/idx FIFOs | Result depth2: count2bits0..3, pointer1bit; gather FIFOs depth3 | Concurrent beats only, not total32beats/1024elements. Request lane acceptance/final-grant vectors are4bits. Lane outstanding cmd count2bits, not total request count. |

The requester computes `vl_byte/vstart_byte/scaled_vector_len_elements` in64bit `elen_t`, then selects an11bit effective length. For this helper's AluA EW8 stream:256 elements/bytes and origin0. MaskM uses EW64, length4 and origin0, **scale_vl=false**. Ad-hoc MaskB uses length1, scale_vl=false and source lane index; its address offset is `idx >>3`. Do not mistake unselected rescaling arithmetic for its actual one-word gather length.

## Request, Scan and Last Tokens

[Lane sequencer:429](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/lane/lane_sequencer.sv:429) forces balanced MASKU payloads. VL1024 gives256 actual elements/lane. VL1023 gives architectural extents256/256/256/255, but all four preprocessing streams are rounded to256: lane3 supplies one final **dummy index slot**, not an extra architectural destination.

[Lane sequencer:968](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/lane/lane_sequencer.sv:968) gives gather AluA `vstart=0`, rounded VL256. VALU counts8 elements/word and forwards raw index/scalar payloads to MASKU, independent of its result BE ([VALU:179](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/lane/valu.sv:179), 879..1000,1292..1303; [SIMD pass-through:152](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/lane/simd_alu.sv:152)). VALU locally forces vm1 for gather preprocessing, so it does not await a separate lane predicate stream. Its vstart-suppressed BE does not remove the forwarded prestart payload.

[MASKU:1344](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/masku/masku.sv:1344) computes VLMAX in32bit unsigned arithmetic, yielding1024 for e8/m8. Source OOR is `index>=VLMAX` or scalar/high-index overflow, not `index>=VL`. e8 vector indices are8bits; VX scalar is not truncated to8bits. The proposed scalar-slot0 VX/VI0/VI31 select in-range0/31, so larger destination VL does not itself add high source-index or OOR coverage. e8/m8 EI16 would have EMUL16 and is not a legal extra child.

The11bit `vrgat_cnt` starts0, progresses only on admitted FIFO pushes, compares to **VL-1** before increment, and resets on the last scan ([MASKU:1392](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/masku/masku.sv:1392)).

- VL1024: last index1023, local index-slot31; consumes the32nd aggregate index word. It asserts `is_last_req`, then resets scan0.
- VL1023: last index1022, local slot30. Last-element condition releases the entire final balanced index word despite not reaching slot31. Dummy lane3/slot31 is **not scanned or given a FIFO entry/source request**.
- OOR destinations still get an index FIFO item and synthesizedzero; an OOR **final** index emits `no_data + is_last_req` to end lane FSMs. In-range final0/31 uses ordinary data +last, even with an all-off predicate.
- Request FIFO waits for all4 lane handshakes, using a4bit accepted mask ([MASKU:622](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/masku/masku.sv:622)). The lane FSM consumes final no_data without a MaskB allocation, or final data with a one-word request ([lane sequencer:249](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/lane/lane_sequencer.sv:249),1244). Its small outstanding count bounds buffering, not global length.

## Four Packed Masks and32 Output Words

[MaskM override:1224](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/lane/lane_sequencer.sv:1224) fixes gather predicate origin0 and length `ceil(VL/(4*64))`. Both1023 and1024 need **four64bit mask words per lane /four256bit aggregate mask beats** (16 lane transactions), not four total lane words. PriorVL512 needed two aggregate beats.

Mask words are deshuffled by actual historical `eew_vmask` ([masku_operands:116](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/masku/masku_operands.sv:116)). The8bit bit-selector counts0..255 and acknowledges at255 or final `issue_cnt_d==0`. Consequently it releases at global255/511/767/1023 for VL1024; at255/511/767/1022 for VL1023, discarding the unused final packed bit. Predicate data zero is still valid data and does not suppress handshakes.

Each destination consumes one issue element, independent of predicate; publish occurs at output slot31 or final issue0 ([MASKU:1477](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/masku/masku.sv:1477)). BothVLs produce32 aggregate output words. The32bit sequential BE accumulates `(vm | maskbit) && (absolute_destination >= vstart)` and is shuffled with EW8, then ANDed with per-lane tail BE ([MASKU:969](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/masku/masku.sv:969),1023,1450). Descriptor construction uses this accumulated BE **before** the later procedural clear/reset; do not infer an all-one final BE from the post-publication default.

- VL1024 final word: remaining32, quotient8/remainder0; per-lane tail counts8/8/8/8, BEff for an otherwise enabled full word.
- VL1023 final word: remaining31, quotient7/remainder3; counts8/8/8/7, tail BEs `ff/ff/ff/7f` before predicate/prestart masking. Global1022 maps sequential byte30 to shuffled byte23: lane2 byte7. Dummy global1023/lane3 byte7 is disabled.
- VL1024/start1023: only last destination is eligible. Sequential BEbit31 maps to shuffled byte31: **lane3 byte7, BE80**, all other lanes00 if predicate1023 is enabled. Output address `vaddr(v24)=96 + iteration31=127 = vaddr(v31)=124 +3`; it reaches the last byte of v31. All earlier1023 bytes stay91.
- VL1023/start1023 has **no body**, not a dummy-lane write test: dispatcher prevents backend issue for vstart>=VL and resets successful vstart ([dispatcher:5970](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/ara_dispatcher.sv:5970)). Its helper/CSR/full oracle still executes architecturally.

`processing_cnt` does not saturate on publication: VL1023 last31-32 becomes2047 in11bits ([MASKU:1626](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/masku/masku.sv:1626)). The final descriptor already used31; issue reaches0 and removes the issue context, whereas commit subtracts32 **with saturation**. Completion does not test processing==0. Queue depth1 prevents replacing a live commit context; next acceptance reloads all counters from newVL and clears slice counters (MASKU:1780..1805,1914). Thus this residue alone is not a falsifiable correctness failure. A probe showing a further issue/publication from2047, incorrect final tail BE, or acceptance without reinitialization would distinguish a real leak; this note makes no RTL change.

## All-Off Completion / Grants

All-off full VL still scans1023/1024 indices and requests in-range source0/31; masking only clears destination BEs. It publishes all32 aggregate results with **BE00 in each lane**, preserving oldvd. "No VRF write" must mean **no byte changes**: actual request/arbitration/write-intent transactions still occur, with wen1 and BE0.

The requester stream register's normal grant means **buffer accepted**, not SRAM committed. Actual bank arbitration uses request-valid, not `|BE`, and directly acknowledges winners; `masku_result_final_gnt_o=masku_result_gnt` is the bank-winning grant ([requester:151](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/lane/operand_requester.sv:151),174,924..969,1068..1086). BE0 is carried into the byte-enabled SRAM with no special completion suppression ([regfile:89](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/lane/vector_regfile.sv:89)).

MASKU records final grants per lane, clears a lane's prior final flag on acceptance of its next queued beat, and drains a result only after normal acceptance plus required final-grant condition ([MASKU:1662](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/masku/masku.sv:1662)). For gather, commit is in **elements**, decrement32; the early-drain condition uses `commit_cnt > 4*64 =256`, not32. This is a more conservative final-write fence for the last up-to256elements, not a width limit. AtVL1024 the first24 queue drains may bypass final flags; the final8 require them. AtVL1023 the first24 may likewise bypass, leaving255elements for the final8. Done still requires commit0 and all4 accumulated final grants; BE0 cannot bypass or forbid this.

Lane VALU completion independently requires no remaining issue/queued result for the current id; main sequencer tracks PE done flags ([VALU:1233](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/lane/valu.sv:1233), [ara_sequencer:551](/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src/ara_sequencer.sv:551)). Static dataflow provides the needed completion route, **not an arbitration-fairness or race-free liveness proof for every history**.

## Falsifiable Boundary Probes (Not Launched)

Use accepted **preedge** valid&&ready samples for counts, not settled final values alone. Keep actual instruction id/op/VL/vstart and old/source layout tags. Only a concrete mismatch warrants a subsequent bounded targeted capture; this note does not authorize it.

| Alternative hypothesis | Minimal distinguishing signals / expected observations |
| --- | --- |
| Global VL or per-lane length truncates | `pe_req_i.vl/vstart`, lane `vfu_operation_d.vl`, AluA request `vl/vstart/eew`, requester `len`, queue `cmd.elem_count/elem_count_q`:1024 global,256 lane, origin0,32 lane words. |
| Fourth mask beat missing / bit scan wraps incorrectly | MaskM request VL4/EW64/origin0, source address sequence0..3, `masku_operand_m_valid/ready/m_seq`, `in_m_ready_cnt_q`, issue absolute index at255/511/767/final; four aggregate consume handshakes, zero mask data still valid. |
| Last index / dummy lane gets lost or extra request | `vrgat_cnt_q`, input `in_ready_cnt_q`, idx/req FIFO push/pop/head, `is_last_req/no_data`,4lane accepted mask, lane `vrgat_state`: final1022 vs1023, exact1023/1024 entries, dummy skipped, all lane FSMs exit after final token. |
| Final destination/prestart BE or address is wrong | `issue_cnt_q`, `processing_cnt_q`, `out_valid_cnt_q`, `iteration_cnt_q`, `be_vrgat_seq_d`, `be_masku_alu_shuf`, queued BE/address/id:VL1023 final tail lane3 BE7f; VL1024/start1023 enabled final only lane3 BE80/address127. Inspect the queued descriptor before reset. |
| BE0 is silently dropped or final grant mismatched | MASKU result req/normal gnt/final gnt, requester internal stream valid/ready/id/addr/BE, actual bank request/grant/wen/BE, `result_final_gnt_q/d`, queue occupancy and `commit_cnt_q/d`:zero-BE transactions accepted/committed, final4flags then done; no destination byte changes. |
| Final `processing_cnt` residue leaks to next helper | Observe last31->2047 atVL1023, issue valid falls, no further publication; next accepted context reload/clear, correct tags and source conversion completion. A2047 value alone is not a stall signal. |

## Natural112 History / Oracle Value and Limits

Re-read original archived e8/m8 helper source (not active outputs): [scenario.c:60](/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/gather_original_review/e8_m8_ops1_prefix66_prepare01/prepared/gather_prefix_e8_m8_ops1/original/scenario.c:60), [operations.S:23](/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/gather_original_review/e8_m8_ops1_prefix66_prepare01/prepared/gather_prefix_e8_m8_ops1/original/operations.S:23), and prior [natural112 plan](NEXT_FULL_SCALAR0_BLOCK_PLAN01.md). C SHA `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`; e8/m8 operations.S SHA `6210a2d96c74a3d15b331b1aeff3d2a1eef01fc64d7becafbc53a042b3460824`; archived VX Linux ELF SHA `7b6623f49a5aee9ae03a3365dc69e898b922ffc61a113c58aae71f96342c83cf`. No new112 program/reference was prepared or run here.

- First112 is exactly seed0/scalar-slot0:7lengths*4masks*4trials, with all111 predecessors. Calls65..80 useVL512,81..96 VL1023,97..112 VL1024. Starts for1023 are1/511/1023/1023; for1024 are1/512/1023/1023, **not1024**. Duplicates are authentic history, not redundant records to delete.
- VL1024/start1023 modesall-on/odd enable the final byte; `i%7==2` andall-off disable it (1023%7=1). Natural calls99/100 and103/104 therefore discriminate final BE80 versus BE0;107/108 and111/112 preserve the final byte while still requiring backend stream completion. VL1023/start>=VL trials are frontend no-ops and cannot claim backend all-off completion by themselves; lower starts in all-off mode do exercise that path.
- Preserve original xorshift/source arrays, all128 predicate bytes, whole oldvd91, source/index/oldvd loads, masked gather, `mv t3,a6`, exact original13asm, CSR setup/readback, fullcap store and each predecessor's scalar oracle/both guards. Loading/storing the entire group in66 is not the same coverage as target writes/scanning into v28..31. Do not substitute isolated upper-VL calls or arbitrary warmups.
- At cap1024 full112 must check **114688 outputs +224 guard values**,1456 helper retirements and112 returned-vstart0;114912 scalar result/guard reads on success. Sparse masks/prestart/tail compare91, active VX0/VI0 compare original e8 input0 (185), VI31 compares original e8 input31 (177), not the e16 values61881/32689. Source legality uses cap, not VL.
- This extension discriminates new fourth-mask-word/upper-half destination/dummy/final-BE/completion behavior in an authentic intra-child history. It does **not** cover higher VX scalar slots/OOR tokens, all source indices, vm1, other seeds, arbitrary arbitration/history, exact unknown archived stopped tuple, Linux schedule, full2688 child or full parent sequence. First112 is1/24 of2688;2576 calls still outside scope. The current66 only reached targetVL512 all-on; this static note closes no further numerical or historical record.

**No new acceptance or launch follows from this note.** Width arithmetic is conditional on the pinned M6 configuration and inspected paths; measurement/full original oracle and actual completion evidence remain required for any future boundary acceptance.
