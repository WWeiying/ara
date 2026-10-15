# Remaining Gather Source Plan 01

2026-10-11. Read-only archive/RTL review; only this document was created.
No build, host/Spike execution, DUT launch, live-process inspection, or sealed
input modification. This supersedes the next-selection recommendation in
[NEXT_GATHER_STALL_PLAN.md](NEXT_GATHER_STALL_PLAN.md), not its historical evidence.

## Decision and Scope

**Next discriminating preparation: original `e16_m8_ops20`, natural first98
calls, retaining all97 predecessors.** Next distinct decode probe would be
`e16_m8_ops3` (vi31), also natural98. These are proposed source-prefix ports,
not recovered stopped tuples, full-child acceptance, or authorization to run.

Do not repeat the user-reported accepted e8m4 vx98, e8m4 ei16 prefix98,
e16m8 vx98, or the started e8m8 vx66. Their current services were not queried.
Their beyond-prefix histories remain untested at full original-child scope.
Seven operation/shape children still lack those dedicated prefix acceptances:
vi0/vi31 at e8m4, e8m8, e16m8, and ei16 at e16m8. This is not seven new
proven RTL defects; all eleven original stalled-child identities remain distinct.

## Original Identities

Paths below use:

- `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`
- `P=C/rvv_permute_partitions01`
- `R(N)=C/rvv_recovery08_N/terminal_scene`
- Each suffix denotes `rvv_permute_restart_<suffix>`.
- Original ELF: `P/release/binaries/<name>`; matching scene ELF: `R(N)/<name>`.
- Assembly/header: `P/<name>/operations.S`, `operations.h`; report: `R(N)/report.json`.

Fresh read-only checks matched all11 ELF hashes to both the scene copies and
manifest/triage, and all11 report hashes to triage. Disassembly at the archived
last/head PCs matched the target encoding and subsequent `csrr a0,vstart`.
The assembly files were read; no new ELF was compiled or claimed byte-equivalent.

| Child suffix | Recovery | Target PC / encoding | Original ELF SHA256 | Next-plan status |
| --- | ---: | --- | --- | --- |
| e8_m4_ops1 | 154 | 105dc / 308e4c57 | `8f5fd128fdc39014de31bd72f9e997f76d07382ee6268d7e6da83a59b7ddfcd8` | Reuse accepted98 |
| e8_m4_ops2 | 155 | 10600 / 30803c57 | `498805cf438a11729e74f0ac7b74068fa5e19bbcf56318790b01afc798d18b65` | Remaining vi0 |
| e8_m4_ops3 | 168 | 1063e / 308fbc57 | `a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b` | Remaining vi31; process-history caveat |
| e8_m4_ops20 | 169 | 10980 / 38880c57 | `15469ee7ca24fd7a7dac6e282358872a5d9c3dfc836e5de363661925fac70c18` | Reuse accepted98 |
| e8_m8_ops1 | 171 | 105dc / 308e4c57 | `7b6623f49a5aee9ae03a3365dc69e898b922ffc61a113c58aae71f96342c83cf` | Already started66; do not duplicate |
| e8_m8_ops2 | 172 | 10600 / 30803c57 | `cc5015d9e7838bfc4f0d4f2b0627e6a08930bd4058b12651a4f988a5c9b1d712` | Remaining vi0 |
| e8_m8_ops3 | 173 | 1063e / 308fbc57 | `ef3a7ff6d6dc48a7e5f20adbb7954490c08c7cbbdcd03afe9bbd4859dee7580c` | Remaining vi31 |
| e16_m8_ops1 | 175 | 105ee / 308e4c57 | `25c6f4e22b01d0d1457c18e289cca6fe7cd3e85113175a3c9e5c82e3d56c3d2a` | Reuse accepted98 |
| e16_m8_ops2 | 176 | 1060e / 30803c57 | `13a9b694ade91e25687108b4bf93b50ecc2d80c3a2a6fd532b269dac3b4aafcf` | Remaining vi0 |
| e16_m8_ops3 | 177 | 1064a / 308fbc57 | `16a715c87479c206545de7e5e9173fcd5ac93a48fe71a6c9dcfd7466993bd853` | Second discriminating choice |
| e16_m8_ops20 | 178 | 10994 / 38880c57 | `21a28efe2ef7b79f9511c9b793bf0235bbc81944b27f1196179642f2a5a8c888` | First discriminating choice |

All11 manifest configurations are2688, and all11 triage `last_trial` fields
are null. Last DETAIL is VL256/start128 for cap512, VL3/start1 for e8m8;
it is printed **after** a returned helper, not before the stalled call.
VL256/start128 is child call66; VL3/start1 can be call49 or50. Neither identifies
the later unreturned call. Target+4 head PC does not prove that CSR read retired.
Earlier numerical prestart overwrites and subsequent no-retirement symptoms
must not be silently combined into one measured root cause.

Recovery168 additionally ran four separate processes, ops8/9/10/11, each
PASS2688, before the stalled ops3 process. The other ten list their stalled
child first. A baremetal ops3 child does not reproduce that Linux process
history; no invented warmup can substitute for it.

## Exact Source, History, and Oracle

Shared original C:
`C/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`, SHA256
`b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`, matches
`P/manifest.json:source_sha256.permutation_oracle.c`.

Every complete child has3 seeds x8 scalar slots x7 VLs x4 mask modes x4 restart
trials =2688 actual helper calls. Preserve the selected-op mask and original
iteration order; do not turn vi's eight scalar slots into one merely because
the immediate ignores the scalar argument. They are distinct vector histories.
RNG is initialized per seed to `0xe736815b449aec21 ^ seed`, then xorshift13/7/17
per element. Inputs, both index arrays, predicate, old-vd initialization and
all13 helper instructions remain original. Nonselected-op filtering may only
be optimized with explicit source-order/state equivalence proof.

- `cap=512` for e8m4/e16m8; `cap=1024` for e8m8 at VLEN1024.
- VL order: 0,1,2,3,cap/2,cap-1,cap. Starts:1, VL/2,
  `(VL<=1023 ? VL : cap-1)`, cap-1. Duplicate starts are retained.
- Masks: all-on, odd elements, `i%7==2`, all-off. All target instructions are
  encoded masked (`v0.t`); all-on mode is not `vm=1` coverage.
- `indices16[i]` follows i%6:0,1,cap-1,cap,cap+1,RNG%(cap+32).
  Ordinary e8 indices truncate; ei16 indices do not. No random reseeding per call.
- Old output and both guards are91. For every element0..cap-1, expected is91
  outside `[start,VL)` or when masked off. Otherwise gather uses original
  input[index], or0 for index>=cap. Index is scalar for op1,0 for op2,31 for
  op3, and `indices16[i]` for op20. This permits source elements beyond VL,
  not merely below VL. `tu,mu` requires exact prefix/tail/masked-off preservation.
- Check fullcap scalar output, both guards and returned vstart0 after **every**
  helper. Original CSR oracle is returned vstart, not a new fflags/vxsat promise;
  existing reference checkers additionally verify actual vset/VL results.

For e16m8 the13 instructions are: fullcap vset; vle16 v8; vle16 v16; vle16 v24;
vlm v0; requested-VL vset; mv t3,a6; csrw vstart,a7; target; csrr a0,vstart;
fullcap vset; vse16 v24; ret. Preserve even unused index loads and scalar moves
for vi. e8m4 ei16 instead uses e8 data loads/stores but vle16 for v16 indices.
The groups are disjoint, so these records do not supply gather-alias coverage.

Natural98 ends at seed0/scalar-slot0/VL512/mask0/trial1/start256 for cap512.
Natural66 ends at seed0/scalar-slot0/VL512/mask0/trial1/start256 for cap1024.
These endpoints inherit the companion op0 localization boundary described in
NEXT_GATHER_STALL_PLAN, **not an exact stopped-tuple discovery for these11**.
Counts are respectively50176+196 and67584+132 output+guard checks, plus98/66
returned-vstart checks. The full child requires1376256+5376 checks at cap512,
or2752512+5376 at cap1024, plus2688 returned-vstart checks. Prefix98 covers all
four masks at VL256/511 but only all-on at VL512; prefix66 has only all-on at
VL512 and does not reach VL1023/1024 or later scalar slots/seeds.

## Static Path Discrimination

References are current repository RTL, not evidence of a new execution:

1. `hardware/src/ara_dispatcher.sv:2050` onward decodes vx from rs1 data;
   `:2298-2328` decodes vi with `use_scalar_op=1`, and the gather branch
   explicitly overrides signed-immediate default with unsigned5-bit extension.
   Both issue `VRGATHER`, use the same vm and data-source layout metadata.
   vi0 and vx0 therefore converge on the same backend scalar index; vi31 adds
   a useful zero-extension check and a nonzero source offset. It does **not**
   have a separate mask source. Masked results must still preserve91.
2. `hardware/src/lane/lane_sequencer.sv:968-991` requests origin0 AluA indices
   for vector gather, fixed EW16 for ei16, balanced ceil(VL/4) lane lengths.
   Scalar vi/vx has no vs1 operand request (`use_vs1=0`), but still uses the
   ALU-result valid/ready stream to advance MASKU's element scan. Real gathered
   data uses ad-hoc MaskB at `:1244-1262`, not the ordinary AluB source queue.
   The final predicate override at `:1223-1230` is decisive: MASKU's MaskM
   starts at0 and requests ceil(VL/256) packed words, for vi, vx and ei16 alike.
   The earlier default vstart-based MaskM assignment is not the final request.
3. `hardware/src/masku/masku.sv:1344-1429` scans from0, extracts vector indices
   or overrides with the scalar's low16 bits plus upper-bit overflow. Index
   FIFO push and counter advance require actual all-lane ALU validity and FIFO
   space. Out-of-range indices suppress data reads; an OOR final index still
   emits a no-data end token. Scalar vi0/31 is in-range at both capacities, so
   it cannot substitute for ei16's mixed OOR/data sequence. Destination BE at
   `:969-993` independently qualifies architectural vstart and predicate.
4. `hardware/src/ara_dispatcher.sv:1794-1813` computes index EMUL=LMUL*16/SEW.
   **Both accepted e8m4 ei16 and proposed e16m8 ei16 have index EEW16/EMUL8**,
   using v16..v23 and cap512. This is not a new larger index-EMUL boundary.
   Data/destination change from e8 m4 v8..v11/v24..v27 to e16 m8
   v8..v15/v24..v31. `masku.sv:1907-1914` and `lane/valu.sv:879-883`
   keep effective index EEW16:16 indices per aggregate256-bit ALU beat;
   output capacity changes from32 e8 elements to16 e16 elements per aggregate
   data word, i.e.2 index beats/output word becomes1:1. This and data EEW/layout
   are the genuine added discriminator. e8m8 ei16 would require reserved EMUL16
   and is explicitly absent from the authentic manifest; do not add it.

## Minimal Next Steps and Falsifiers

**First: e16_m8_ops20 natural98.** It compares against accepted e16m8 vx98
(same data shape/history boundary) and e8m4 ei16 prefix98 (same index EEW/EMUL).
Preserve the original first97 calls and full oracle, rather than extracting
VL512/start256. Call66 also exercises VL256/start128. At VL256, last index
`indices16[255]=512` is OOR and must deliver an end token; at VL512, last
index `indices16[511]=1` is in-range. These give both terminal paths in one
authentic prefix. Prefix/tail preservation remains checked throughout.

Only if later authorized evidence fails, use a bounded window around the last
target and distinguish these hypotheses with handshakes, not asserted-valid
cycle counts:

- Wrong index origin/layout: capture request op/eew/vl/vstart/scale_vl,
  AluA command and operand accepted words, `masku_operand_alu_seq`,
  `vrgat_cnt_q` and `vrgat_req_idx_d`; expected index at scan0 is0 even when
  architectural start is128/256. Check actual request origin0 rather than
  inferring it from final zeros.
- Wrong mask/BE qualification: correlate MaskM accepted word index and data,
  architectural vstart, issue/output counters, `be_vrgat_seq`, and result
  grants against original predicate and window. Same mask supply applies to vi.
- End-token or backpressure defect: correlate index/request FIFO push/pop,
  `vrgat_req_no_data_d`, `vrgat_req_is_last_req_d`, per-lane MaskB request/
  valid/ready, result queue occupancy/grants and done. A final OOR index needs
  no data read but does need all lanes to finish. Mask-off does not authorize
  dropping the sequencing token.

**Second, conditional: e16_m8_ops3 natural98.** Original target is vi31, not
rewritten vx31. Verify scalar_op31, overflow0, source input[31] and the full
independent output oracle. A signed-immediate decode would instead produce
OOR zeros. Element31 is the high16-bit element of lane3 in aggregate data
word1 (four64-bit lanes), a different access than vx0. Do not assert it crosses
a physical vector-register boundary. Defer vi0's lower-discrimination duplicate
backend path, and retain all six vi-child identities as open until tested.
e8m8 vi31 is a later distinct cap1024 probe, not permission to repeat vx66.

## Cost and Admission Limits

No reference execution or retirement measurement exists here for the seven
remaining proposed ports. Reuse measured reference costs only as comparators:

| Existing comparator | Retired to success | Provenance |
| --- | ---: | --- |
| e8m4 vx98 | 2092785 | NEXT_GATHER_STALL_PLAN, accepted M5 prefix audit |
| e8m4 ei16 prefix98 | 2225267 | Same audit; M5 DUT3257.146s |
| e16m8 vx98 | 2002820 | e16_m8_ops1_prefix98_audit01/REVIEW.md; Spike3.327266s |
| e8m8 vx66 | 2745395 | e8_m8_ops1_prefix66_audit01/REVIEW.md; Spike4.530459s |

For proposed cap512 prefixes, a **static planning envelope**, not measurement,
is roughly2.0..2.23M retired using those neighboring source ports. At prior
M5 throughput683 retired/s this is49..55min; at the older conservative273/s
it is122..136min, or147..164min with20% margin. vi/ei16 differences and future
load may invalidate this envelope; actual reference instruction cost is required
before admitting any fixed timeout. The source has no new huge scalar matrix.

For a future e8m8 vi66, the existing2.745M comparator implies67..168min over
the same throughput range, and conservative+20% is201min: no guarantee of
completion under3h. Do not shrink its oracle or retry with an enlarged budget.

Complete2688-call children are materially different jobs. Merely scaling the
prefix instruction costs by2688/98 or2688/66 gives roughly55..61M or112M
retirements, respectively; this is a crude extrapolation, not a reference result
or rigorous bound (VL mix, initialization amortization and op cost differ).
At683/s even those estimates are22..25h or45h. They are **not** proposed as
<=3h runs. Original full-child closure remains deferred pending authentic
full-source cost evidence and separate authorization, not replaced by prefix
PASS or by isolated tuples. Original Linux process history remains another gap.

Future preparation should reuse the existing immutable prefix preparation and
strict checker contracts in a successor directory: original C diff proof,
selected13-instruction byte comparison to the archived ELF, exact setup/vector/
fullcap+guard/CSR checks, source/ELF/image pins, raw DETAIL/FAIL veto, completed
prefix marker and successful firmware/process exit. A new baremetal ELF is a
source port; a byte-identical rebuild of the original Linux ELF is not established.

## Identity Anchors for This Review

```text
triage.json            eb87f0ed9c07b3978e91e35ff5bcc0824388beb312510ba942ef061c0f63043f
P/manifest.json        6e6c083670aaf312e9eeb252e576ec88cd5fe3a94b415c3f619c2bb9e7c43e58
P/parent_mapping.json  46b142c59ce1bf63e122355bba5ca03f86b8a0e63dc5237826f3afa68062c1d9
e8m4 operations.S      118a8c9572532a2b332749165cff3cea9323a49722641dcf64b14fd501ccd774
e8m8 operations.S      6210a2d96c74a3d15b331b1aeff3d2a1eef01fc64d7becafbc53a042b3460824
e16m8 operations.S     40bce22639d00865881e06337270ed76fd37e01c7891296471934accbf7afbcf
ara_dispatcher.sv      c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d
lane_sequencer.sv      c11e2a871b91a7aaf940f9e4fb0ef79229a48a2a9b7e2db3fd1108e24dc01dcc
masku/masku.sv         1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d
lane/valu.sv           f8a8cd12e9d4732eca87e1c9a1aa48b52a8e684f2d7e64d0e8ec1faa9411c778
```

Assembly SHA is identical across selected-op children of each shape; operation
selection resides in C build parameters. All eleven historical stopped tuples
remain unknown. No new PASS, common-root-cause claim, or full-child closure is
created by this plan.
