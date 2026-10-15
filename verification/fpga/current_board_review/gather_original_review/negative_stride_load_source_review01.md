# Negative Stride Load Source Review01

2026-10-12. Independent static review only. No running CSV/log was read;
no compilation, reference, simulation, service query or RTL/producer edit.

## Verdict

The selected source single and proposed geometry in `next_failure_priority01.md`
are consistent. No concrete defect in that selection or still-unfixed M6 RTL
root cause was established. This is not adapter/DUT admission: Tesla's new
adapter is not reviewed or accepted here. Requirements below are binding scope
checks, not claims that an unfinished adapter has violated them.

The actual archived single failed on an inactive element's address and wrong
vstart. Current M6 contains predicate gating and load prefix-drain repairs that
directly cover those paths. A source-faithful one-fault/retry discriminator is
justified; inventing predecessors or changing RTL from this old failure is not.

## Authentic Program And Failure

Archive root H:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_negative_stride_handoff01`.
Single S: `H/singles/rvv_small_fault_strided_negative_stride_e16_m1_u1_s0_b3_m2_f0_g3`.

Rechecked SHA256:

| Artifact | SHA256 |
| --- | --- |
| next_failure_priority01.md | 473410ca4e8e4b22bd9e931715242eb0cf5257ab8139629f368c9749d92a91e3 |
| S/scenario.c | 90996937a77228ac31baf0323079d97e8c5004fad163e80a950ac670b82eb563 |
| S/scenario.S | 597a58a41e73941a90e3ccc015676dca606d9f6f74436b2965dede15bfab3039 |
| S/scenario.elf | 4c10f89aeb0d400412b15115b48ad3f11d9296fc881fb2645e573a5807d0e907 |
| S/case.json | 90e2325772d69fc5353e3cde71e1cb7562b62d863fd68920b562ea8b92057e41 |
| H/evidence/single_board_report.json | 9765d4734ef678223be145e14c2f2bc4ea1458bc5f2ab3a3a49321ed185a3bf9 |
| H/evidence/single_manifest.json | dc879ed4509e0f801ceb6e15a19c519707ed258c2963d42df87a76b36fc76c2f |
| H/controls/rvv_trace_fault_baseline_strided_negative_stride_e16_m1/baseline.c | 631da853fe5939e2a812145d23155767d4e803f3d9aa22133187d6455905588a |

Original control and reconstructed baseline ELFs both hash
`1bfbb55bb01dc16c4f309fdc3a23f969026912acf8819f8edbfe99fd852d4885`.
Diffing that baseline C against S/scenario.c finds only the exact selector and
BEGIN/CONTEXT/RETURN/CHECK diagnostics. Geometry, initialization, signal handler,
poisoning and scalar oracle are unchanged. This preserves authentic single
source provenance; it does not make the diagnostic single ELF byte-identical
to its parent. `original_rebuild_byte_identical=false` and archived per-trial
original-history equivalence limits remain valid. No new rebuild was attempted.

Read-only disassembly of the actual failed ELF confirms capacity at 0x109f6,
load helper at 0x109fe, and target 0x10a12 / opcode09c55c07. Its ten instructions:
capacity vset; v24 preload from a2; **ld t3,0(a5)**; mask load from a3;
VL8 e16/m1 tu/mu setup; masked vlse16; immediate csrr vstart;
capacity restore; full v24 store; ret. Do not substitute a generic helper,
store, x0 stride, or Gather's thirteen-instruction accounting.

The actual board result is failed/int exit1/0.21995549975 seconds:
address272794079230 versus expected272794079214; PC68114 matches0x10a12;
vstart3 versus5; VL8/vtype8; returned status0/faults1/handler_errors1/errors1.
The combined context check already accounts for that one error. The source
oracle/report establish no additional returned-vector or memory mismatch; there
is no archived raw VRF dump in this reviewed evidence. `case.json` instead
contains a different full-trace address/PC68134: do not merge its absolute
addresses with this independent single's execution.

## Geometry And Restart State

Let M be the start of the 8KiB mapping, P=M+4096. NF1, boundary3, split0,
gap3 and halfword size2 give positive step8, target=P+3*8-2=P+22,
then signed stride=-8. Mask byte0x24 selects elements2 and5 only.

| i | Address | Active | Required first attempt |
| --- | --- | --- | --- |
| 0 | P+22 | no | skip |
| 1 | P+14 | no | skip |
| 2 | P+6 | yes | load original0x287a and commit |
| 3 | P-2 | no | skip without target translation/AR |
| 4 | P-10 | no | skip without target translation/AR |
| 5 | P-18 | yes | load page fault; vstart5 |
| 6 | P-26 | no | skip on retry |
| 7 | P-34 | no | skip on retry and finish |

All accesses are halfword aligned and no halfword straddles the page boundary.
The old address delta16 is exactly element3 versus5, not a split-field fault.
Descending virtual addresses do not reverse the increasing element ordinal.

At the fault, the original saved-v24 oracle checks elements0..4: only element2
is0x287a; the other four are0x005b. Restore/remap **the lower page**, refill all
2048 halfwords using the original formula, then poison the single completed
active element2's source at P+6 to0x2821 (=0x287a XOR0x5b). It is not a
two-element poison prefix. Leave saved target PC, vstart5, mask and vd unchanged.
Retry that very target PC, with base argument still P+22 and t3 still-8;
AddrGen's resumed effective address becomes P-18. Do not pass P-18 as base
while also retaining vstart5 (that would apply the offset twice).

Final v24[2] must remain0x287a despite memory[P+6]=0x2821; v24[5]=0x26be.
All other62 result elements remain0x005b. Restarting at0 reloads the poison;
skipping toVL8 leaves element5 old. Reloading vd/helper setup before retry
destroys the committed-prefix discriminator.

## Full Oracle And Adapter Boundaries

- Require actual vlenb128 and original capacity return64, not constants standing
  in for observations. Physical CAPACITY_LIMIT128 is not dynamic cap64.
- Preserve physical input128 halfwords (initialize the first64 to101+13*i),
  all128 offsets with the original slot formula, output130 halfwords all0x5b,
  and all16 mask bytes0x24. The capacity64 mask load consumes8 bytes. Do not
  shrink physical storage or claim that all128 inputs were source-initialized.
- Preserve both initial page fills: 4096 halfwords total; on repair, refill2048
  lower-page halfwords, then poison only P+6. Final memory oracle reads all4096
  halfwords, expecting `uint16_t(((A-M)/2)*37+11)` everywhere except P+6 XOR0x5b.
- Preserve64 final output loads plus guards output[0] and output[65]. Physical
  output[129] is not the original upper guard; any added extra-storage checks
  must be labelled separately. Check prestart/inactive/tail, not only2 actives.
- Require one load fault, target PC/tval=P-18/VL8/vtype8/vstart5, original
  saved-prefix checks, same-PC retry, immediate returned vstart0, full oracle,
  original successful exit. Handler prefix checks and final checks are distinct.
- A real Sv39 adapter must begin with the lower leaf invalid, upper leaf valid,
  then map a correctly aligned readable lower backing page and fence/SFENCE the
  repair. Bare mapped RAM, a protection-only test, or a synthetic CSR fault
  does not reproduce original unmap/remap semantics. Scalar physical refill
  must not cause an unintended handler fault.
- S-mode target execution with an M-mode observer reports mcause13/MPP=S;
  it is not a Linux SIGSEGV/SEGV_MAPERR or Linux signal-frame replay. Preserve
  target GPRs, particularly a0/a2/a3/a4/a5/t3, v0 and v24 across observation.
  If snapshot vset changes VL/vstart, restore VL8/e16m1 and vstart5 before MRET;
  never reconstruct prefix vd by software. Check actual MRET PC/context, not
  merely a stored desired retry PC. Count a completion ecall separately from
  the one load fault.
- Existing `masked_translation/sv39_extended/fixture.h` row3 is a store,
  offset4106/stride-4/cause15. Its generic repair only installs the leaf, without
  the original full lower-page refill. Its snapshot/CSR/return machinery is
  reusable, but those stimulus/repair details cannot be reused unchanged.
  The original handler checks only the five pre-fault values; do not silently
  advertise a newly strengthened snapshot oracle as an original source check.

## M6 Static Path And Discriminators

Frozen snapshot settings are nr_lanes4/vlen1024. The following live files were
byte-compared with M6 frozen sources, with identical contents:

| File | SHA256 |
| --- | --- |
| hardware/src/vlsu/addrgen.sv | 470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da |
| hardware/src/vlsu/vldu.sv | 4e46a4733530b15edb05bbaded651899511af930e2caffe77b7482528c4fc8ab |
| hardware/src/ara_sequencer.sv | bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655 |
| hardware/src/lane/lane_sequencer.sv | c11e2a871b91a7aaf940f9e4fb0ef79229a48a2a9b7e2db3fd1108e24dc01dcc |
| hardware/src/masku/masku.sv | 1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d |
| hardware/include/ara_pkg.sv | 49a4fd9879cad35c2c77241bd5114fb8d02ab520e833335fd916122854830971 |

1. AddrGen320/364..383 forms base+vstart*stride, and remaining **bytes**
   `(VL-vstart)<<EEW`. Stride is64-bit elen_t; -8 isfffffffffffffff8.
   Unsigned bit-vector arithmetic preserves the required modulo64-bit signed
   address increments here. No sign-width defect is demonstrated for this case.
2. AddrGen604..633 selects an owner-tagged predicate window and derives element
   `VL-(len>>EEW)`. First attempt len16 counts0..7. At fault5 len6 yields5;
   retry starts len6/addressP-18. Skip descriptors at924..947 advance both
   ordinal bytes and signed address without MMU/AR. Predicate-gated start_req
   at978 and MMU request1172..1177 exclude inactive elements3/4.
3. Lane sequencer1224..1240 requests the packed mask word containing vstart,
   not a data-EEW offset. MASKU1083..1093 aligns the EW16 data window to16
   elements; retry5 still has first_element0/read_count8. Owner/window/valid
   must belong to the retry load, not stale fault/preload context. VLDU's mask
   spill retains owner/first_element and drains the owning mask on exception.
4. An active strided load uses AR len0/size1 (one halfword). MMU fault1250..1283
   appends the ordered exception marker and derives vstart from current len,
   not the negative VA/page offset. This ordinary load is not FOF.
5. VLDU356..425 consumes skip descriptors without R beats, advancing byte
   position while predicate BE suppresses their writes. Fault5 follows the
   real element2 payload plus skips. VLDU625..646 queues the partial prefix,
   waits for zero occupancy/valids and **all final grants**, then HANDLE_EXCEPTION
   emits same-owner done and clears counters. Sequencer989..991/1024..1029
   withholds fault response until that load VID completes and operands accept.

A separately authorized measurement should bind accepted request VID/op/base/
stride/VL/vstart/EEW; ordinal/remaining bytes; mask owner/first/valid/active;
skip/exception descriptor push+pop; distinct MMU target requests and accepted
AR/R; v24 result data/BE/request acceptance/**final** grant; owning exception
done/response; fault CSR and actual MRET/retry. Do not count a held valid level
as multiple accesses. For the frozen four-lane EW16 shuffle, element2 bytes4/5
map to lane2 offsets0/1; element5 bytes10/11 to lane1 offsets4/5. These are
VRF result byte positions, not AXI beat positions or virtual page offsets.

FaultP-2/vstart3 discriminates predicate/ordinal failure; correct faultP-18
with stale saved element2 discriminates drain/ownership; correct fault context
but poisoned final element2 discriminates restart/setup corruption; wrong
resumed address discriminates base/stride/vstart handling. None is established
as a new M6 failure by this static review. Any eventual pass closes only this
authentic single's adapter scope, not the original96/Linux ABI or429-record family.
