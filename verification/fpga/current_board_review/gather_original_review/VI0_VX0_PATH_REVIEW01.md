# VI0 Versus VX0: M6 Static Path Review

Read-only source/provenance review, 2026-10-11. No DUT, Host test, Spike, build,
service/process query, RTL change, or sealed-input change. The active e16/vi31
campaign and its outputs were not inspected. Only this new report is written.

## Conclusion And Limits

For **the same architectural/backend state and scalar VX operand exactly zero**,
`vrgather.vi v24,v8,0,v0.t` and `vrgather.vx v24,v8,t3,v0.t` lower to the same
functional backend request and traverse the same lane/VALU/MASKU paths. No
VI0-specific backend branch was found. This is a conditional static equivalence
of functional fields, not a measured whole-request/cycle equivalence or liveness
proof. Instruction encoding, scalar-register dependency, PC, transaction/trace
identity and program history are genuinely different. Matching final values is
not enough to equate stalls or timing.

**No original vi0 child PASS is established here.** Existing VX prefixes do not
close a vi0 child, all2688 calls, the original Linux ELF, parent process history,
or the unknown historical stopped tuple. No remaining stall is waived. Full VX
programs also use seven other scalar values: only their scalar0 subset has this
relationship to vi0, whose index remains zero even when `t3` is nonzero.

## Exact Sources And Existing Controls

Roots:

- `W=/home/wangwy/openproject/ara_dsa_signoff_integration`
- `F=/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources`
- `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`
- `P=C/rvv_permute_partitions01`
- `G=W/verification/fpga/current_board_review/gather_original_review`

The current `P/manifest.json` was read with a JSON parser. Each selected child
has `operation_ids=[2]`, `configurations=2688`, original pass marker
`RVV_PERMUTE_PASS`, and archived timeout600s. That archived timeout is metadata,
not an adequate proposed full-oracle VCS budget. `ops1` is VX, `ops2` is VI0,
`ops3` is VI31. Original helper encoding is respectively308e4c57/30803c57/
308fbc57. All are masked v24/v8 forms; the helper sets tu,mu. Original ELF hashes
below were freshly computed and equal manifest entries, not copied from a PASS
label. Paths are `P/release/binaries/rvv_permute_restart_<suffix>`.

| Original VI0 child | VLEN1024 capacity | Original ELF SHA256 |
| --- | ---: | --- |
| e8_m4_ops2 | 512 | `498805cf438a11729e74f0ac7b74068fa5e19bbcf56318790b01afc798d18b65` |
| e8_m8_ops2 | 1024 | `cc5015d9e7838bfc4f0d4f2b0627e6a08930bd4058b12651a4f988a5c9b1d712` |
| e16_m8_ops2 | 512 | `13a9b694ade91e25687108b4bf93b50ecc2d80c3a2a6fd532b269dac3b4aafcf` |

The preserved assembly in each `P/rvv_permute_restart_<suffix>/operations.S`
contains the same thirteen-instruction helper setup: fullcap source/index/old-vd
loads, vlm, requested VL, `mv t3,a6`, `csrw vstart,a7`, target, returned-vstart
read, fullcap vset/store, return. VI0 **still executes** `mv t3,a6`; it does not
consume t3 at the target. Keep this apparently redundant instruction in a port.

Existing accepted controls are reused, not rerun or upgraded:

| Shape / VX scalar0 prefix | Existing evidence | Acceptance boundary |
| --- | --- | --- |
| e8/m4, first98 | `G/gather_repair05/m5_successor01/prefix_terminal_audit01/audit.json` | M5 prefix,50176 fullcap checks/196 guards; not newly labeled M6 |
| e8/m8, first66 | `G/e8_m8_ops1_prefix66_terminal_audit01/{REPORT.md,audit.json}` | M6 DUT-case prefix;67584 checks/132 guards, not full2688 or outer-service exit proof |
| e16/m8, first98 | `G/e16_m8_ops1_prefix98_terminal_audit01/{REVIEW.md,audit.json}` | M6 DUT-case prefix;50176 checks/196 guards, not full2688 or outer-service exit proof |

These reports were read as existing acceptance, not independently full-CSV
recomputed in this task. Historical identities/unknown stopped-call limitations
are documented in `G/STALL_PARENT_PLAN.md` and `G/NEXT_GATHER_STALL_PLAN.md`.
Last printed DETAIL follows a returned call and is not a unique unreturned-call
marker. Do not silently substitute that tuple for the original history.

## Frontend: What Really Differs

References below use W-relative files; the nine principal reviewed RTL files
were hashed against F and are byte-identical at review time.

1. `hardware/src/cva6_accel_first_pass_decoder.sv:93` declares an integer rs1
   dependency for OPIVX; OPIVI retains the default no-scalar-source setting.
   At220 the predecoder maps the latter source register to x0 and forwards the
   original instruction in `result`. VX names x28/t3 and may wait for scalar
   scoreboard/forwarding; VI0 has no t3 dependency. Both classify as ACCEL_OP,
   with no scalar destination, load or store classification for this target.
2. `hardware/deps/cva6/core/issue_read_operands.sv:654` can forward the VX source.
   `.../acc_dispatcher.sv:345` packs the original instruction from `imm`,
   rs1 from `operand_a`, rs2 from `operand_b`, frm and trans_id, then gates the
   request on nonspeculative issue/commit. At295 these fields pass to Ara.
   Under this predecode VI0's integer source is x0, but dispatcher VI decode
   does not rely on the transported rs1 value in any event. The original CSR
   setup provides another serialization point; that does not prove equal
   frontend timing in every history.
3. The trace's name `cvx_req` is not proof that the generic CV-X-IF FU is used.
   The frozen cv64a6_imafdcv_sv39 configuration has CvxifEn=0; the accelerator
   path uses acc_dispatcher. `hardware/tb/ara_commit_monitor.sv:290` logs only
   accepted instruction/trans_id for cvx_req, not rs1/rs2. An actual scalar
   value needs scalar retirement reconstruction or a focused operand probe.
4. `ara_dispatcher.sv:2049` OPIVX takes `scalar_op=acc_req_i.rs1`; at2298/2321
   OPIVI initially uses a common immediate rule but **VRGATHER overwrites it
   with zero-extended uimm5**. VI0 therefore yields full-ELEN zero. Raw insn
   and FOR_VERIFY `verify_arch_insn` remain different. Dynamic tags, token phase,
   instruction timing and historical request IDs must not be asserted equal
   between separately executed programs merely from matching semantic fields.

## Functional Request Comparison

Assumptions: same VL/vstart/vtype/CSR state, VRF contents, historical EEW labels,
dependency state and target register groups; VX rs1 value0. At
`ara_dispatcher.sv:1204`, defaults initialize all unspecified fields. Decode
at2051-2077 versus2303-2326 gives:

| Field or decision | Both forms under these assumptions |
| --- | --- |
| op / scalar selection | VRGATHER / use_scalar_op=1 / scalar_op=0 |
| source registers | use_vs1=0, vs1=0; use_vs2=1, vs2=8 |
| destination / old-destination operand | use_vd=1, vd=24; use_vd_op=0 |
| predicate | vm=0, packed v0 stream, eew_vmask from the same v0 label |
| lengths and layout | same vl, vstart, vtype, emul=LMUL, default eew_vs1/eew_vs2=SEW; eew_vd_op=eew_q[8] |
| conversion/stride | no conversion, same resize/rounding defaults; stride=0 and therefore is_stride_np2=0 |
| legal group geometry | v8 source and v24 destination correctly aligned and disjoint for m4/m8; no VX/VI distinction |
| layout maintenance | same full-vs2-group reshuffle and masked/partial-destination preservation decisions |

`ara_dispatcher.sv:5329` treats both as full-vs2-group gathers; scalar0 does not
narrow the layout normalization to only register v8. The M6 indexed-memory
`indexed_mixed_vs2_layout` predicate at5342 is for VLXE/VSXE, not these gathers.
Architectural no-ops (vstart>=vl, including VL0) bypass maintenance/backend at
the common guard5349 and completion path5967. A same-state comparison must
include old layout/hazard state, not just SEW/LMUL and scalar0.

## Backend Walk

| Stage | Static path and equivalence |
| --- | --- |
| Sequencer allocation | `ara_sequencer.sv:329` reserves ALU and MASKU for both. Scalar/layout/use fields are forwarded at779; dependency bookkeeping uses decoded register use, not VX/VI func3. |
| Lane issue | `lane/lane_sequencer.sv:381` forwards scalar0, suppresses regular ALU vs2 for gather, and balances lane payload by ceil(VL/NrLanes). At987 AluA push requires use_vs1, false here; at1024 regular AluB gather request is suppressed. Neither form reads vector indices from v16 for the gather itself. |
| VALU preprocessing | `lane/valu.sv:214` replicates scalar bits by SEW, thus zero for both; `lane/simd_alu.sv:152` passes operand_a. VALU forces unmasked preprocessing for MASKU at1294-1302, supplies the same full-length token stream, and at941/1197 directs mask-tagged results to MASKU rather than normal ALU VRF writes. This is not a direct no-token bypass for scalar gather. |
| Index/request FIFOs | `masku/masku.sv:1383` uses the full scalar: low16 index plus overflow from higher bits. Zero is in range for all three capacities. Every scanned destination generates the same index0 and ordinary source request; destination masking/prestart does not suppress these source requests. The final ordinary request carries is_last_req; VI0/VX0 do not exercise an OOR no_data sentinel on an executing instruction. |
| Lane source handshakes | `masku.sv:604` requests vs2 via idx/NrLanes and broadcasts to every lane; per-lane acceptance bits at617 hold each FIFO head until all lanes accept. `lane_sequencer.sv:247` spills/serializes it, counts real MaskB commands, recognizes last/no_data identically, and at1244 requests one source element per lane with the same saved hazards. Do not count mere valid cycles as requests. |
| Source data versus old vd | MASKU's port named `masku_operand_vd` is **vs2 source data** for gather, not an old-v24 fetch. `use_vd_op=0` means no ordinary old-vd operand request. At941 MASKU selects source index0 from the deshuffled data; unchanged destination bytes survive through BE, not a separate old-vd merge read. |
| Mask ownership/consumption | `lane_sequencer.sv:1218` overrides packed MaskM to start at0 and cover ceil(VL/(NrLanes*ELEN)) words. MASKU scans from0 and at1551 advances the predicate only at the packed-word boundary or last issue element. Both retain the same prestart prefix traversal and maskword consumption. |
| Data/BE/results | `masku.sv:968` enables writes only for `(vm || maskbit) && absolute_destination>=vstart`;1465 also bounds active/tail bytes. Result background is ones for gather, not oldvd; disabled bytes are left in VRF. The full queue guard at1458 keeps descriptor/data ownership while stalled. Same source, predicate and prior VRF state imply the same functional data/BE decisions, not guaranteed identical cycles. |
| Completion/CSR | At1670-1740 MASKU drains queued lane grants and required final grants before vinsn_done. Sequencer clears PE-running bits at551 and asserts idle from the running set at88. The helper's `csrr vstart` enters the dispatcher common WAIT_IDLE CSR path4660; early accelerator acknowledgement/reset-vstart at5994 alone is not backend completion. Both use this same ordering. |

There is no new concrete VI0-only RTL fault established by this inspection.
Backend conditional equivalence does not establish complete liveness under
arbitrary backpressure or explain the archived stopped state. A lower scalar
dependency count may change relative queue arrival timing; do not dismiss an
observed VI0 stall merely because the selected index is the same as VX0.

## Smallest Useful Next Original Prefix

Prefer **e8/m8/ops2, original natural first66 calls**, on an independently
authorized frozen image. It changes the frontend instruction form from the
already accepted same-shape M6 VX control, without repeating VX or VI31.
Capacity1024 and endpoint `[seed0,op2,scalar-index0,length-index4,mode0,trial1]`
give VL512/vstart256. Keep all65 predecessors, the original loops including
1792 excluded-op empty iterations before selected op2 in seed0, original RNG,
fullcap loads/stores, all128 predicate bytes, `mv t3,a6`, vstart write/read,
all13 helper instructions and every per-call oracle. The natural prefix includes
all four mask modes at earlier lengths, no-op restart cases and real prestart
state; it is not a fabricated endpoint-only test.

Require66 returned-vstart checks,67584 fullcap result comparisons and132 guards,
normal CSR/exit checks and all original first-error vetoes. Stop only **after**
call66's complete oracle with an explicitly labeled PREFIX result. Do not thin
scalar checking, add warmup/drains, or rename the VX binary as VI0. The original
C expected() at31-35 selects index0 for op2 independently of scalar, while the
whole program still iterates all eight scalar setup values; the prefix only
covers scalar-index0. Beyond-prefix iterations remain open.

Source-derived preparation must bind the actual ops2 archived ELF/S/header,
target30803c57 and original helper order, then separately validate the port.
Original Linux byte-identical C rebuild is not established by existing prefix
ports. No Host/Spike/SoC execution is authorized or performed by this note.

If this single new prefix later stalls, discriminate frontend nonacceptance
from backend blockage using actual accepted acc_req insn/rs1 and ara_req
scalar/use fields plus arch tag, full EEW/reshuffle state, ALU-to-MASKU payload
handshakes, index/request FIFO push/pop, per-lane MaskB valid/ready/no_data/last,
MaskM consumption, output BE/queue grants/final grants and done. A bounded
capture must preserve the original preceding history. Existing CSV cvx_req
alone cannot expose the rs1 value, and finite scalar checking is not deadlock.

## Current Hash Anchors

Fresh SHA256 calculations in this review:

```text
M6 image.json a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0
P/manifest.json 6e6c083670aaf312e9eeb252e576ec88cd5fe3a94b415c3f619c2bb9e7c43e58
original.c b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca
e8_m4_ops2/operations.S 118a8c9572532a2b332749165cff3cea9323a49722641dcf64b14fd501ccd774
e8_m8_ops2/operations.S 6210a2d96c74a3d15b331b1aeff3d2a1eef01fc64d7becafbc53a042b3460824
e16_m8_ops2/operations.S 40bce22639d00865881e06337270ed76fd37e01c7891296471934accbf7afbcf
e8_m8_ops2/operations.h 2f9fcaa9b1deab684890f5b79add2bd06ab481ec8c22e5d42db2dbab7305b4f3
M5 e8m4 prefix audit e368d848ba691608b3349af5b7af73bd51c135b475dc756e5c04766ac43e23f8
M6 e8m8 VX66 audit 7840992136756479dd019a95eab8534a05d99ecb07998e83fa6c698f2eb4a6ee
M6 e16m8 VX98 audit d22348024e99b1eb881192472128e8149ffe3b63041a7fe57aa25843b1d043f7
```

The original C path is
`C/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`.
It is the shared complete permutation source, not evidence that op2 ran.

The following W-relative RTL hashes each equal the corresponding F file:

```text
hardware/src/ara_dispatcher.sv c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d
hardware/src/cva6_accel_first_pass_decoder.sv 79dcb6c3c41b6ce0157f39b0f5d1ea42dcbc58a36b6f743b59b96b9d041594fc
hardware/deps/cva6/core/acc_dispatcher.sv 6aa6fa74eaca4fd9981c4e9849bb4594df016ba4262d47295696aead82eeb117
hardware/src/ara_sequencer.sv bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655
hardware/src/lane/lane_sequencer.sv c11e2a871b91a7aaf940f9e4fb0ef79229a48a2a9b7e2db3fd1108e24dc01dcc
hardware/src/lane/valu.sv f8a8cd12e9d4732eca87e1c9a1aa48b52a8e684f2d7e64d0e8ec1faa9411c778
hardware/src/lane/simd_alu.sv 8d84858bd3dbb3baab5e2b12b8eb0c36cceb407373adee9dc0285ab8dfa962bc
hardware/src/masku/masku.sv 1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d
hardware/src/ara.sv 1d190744249603d6c3d6e2c9c21cd5ac121fee2a9c65f5b227be239c320286da
```

Additional frozen-file anchors:

```text
hardware/deps/cva6/core/issue_read_operands.sv 774692497c689fa166d84ea732aa5b24dd45f9642805263cc2de10f79100028f
hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv 0fbfd7729bce2cc7994686d27ff0adab053c816a958231556c335a09deb18ee3
hardware/tb/ara_commit_monitor.sv 38b7642703c49e31fd0493b81e948388f2dbc72f97da418f3ed76e73bd42c782
```
