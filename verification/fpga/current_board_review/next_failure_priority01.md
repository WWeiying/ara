# Next Failure Priority01

Static selection only, 2026-10-12. No simulator/service query, DUT/reference
execution, compilation, RTL edit or prior-artifact change. This note reads
CURRENT_SCOPE and archived source/evidence, not running NF7/small2 results or
the Gather CSV currently being audited by the parent.

## One Recommendation

Select the independently board-failed single:

`rvv_small_fault_strided_negative_stride_e16_m1_u1_s0_b3_m2_f0_g3`

NF1, e16/m1, VL8, masked negative-stride **load**, stride-8 bytes, mask0x24,
lower page unmapped/remapped, boundary3, split0, gap3. This has an exact
fault-address/vstart counterexample, an archived executable and complete C/S
oracle, and needs no invented warmup or giant parent replay. The existing
extended8 negative-stride case is a **store**, protection rather than unmapping,
stride-4; it does not accept this load/remap/descending-address identity.

**No still-unfixed current RTL root cause is established.** The historical
inactive-element fault is consistent with the already-repaired nonindexed
predicate path. Current source contains that repair and the load fault-drain
repairs. This is the best bounded, exact remaining failure-scope discriminator
found here, not a claim of a new M6 failure or permission to edit RTL.

## Deduplication Against Current Scope

Inspected CURRENT_SCOPE SHA256:
`7e9ecbc03b391baf78a111e1f9120f837a71909385d46b9d3d4f116e0fe93c7e`.
Its latest measured updates override stale pending wording in older tables.

| Remaining evidence class | Disposition for this selection |
| --- | --- |
| NF7 current-image96 and full arithmetic small2 | Running per parent/current ledger. Excluded; no live queries or duplicate work. |
| Recovery168 Gather66 | Parent offline recovery of checker event mismatch. Excluded; not a new DUT failure. |
| NF2 failed singles40 | Latest M6 pilot4 plus remaining34/J4 independently accepted. Do not reuse old table wording to reopen them. |
| RVV07 eleven reductions, FP scalar moves47, integer comparison19+19, Gather83, unboxed265 | Their stated single/prefix scopes are accepted. Full parents/Linux remain separate, not grounds to repeat those singles. |
| Other unit/strided fault records within429 | Exact failed source singles remain beyond selected NF1 extended8, NF2 and positive-stride NF8 coverage. This negative-load single is selected from that gap. |
| RVV04 additional FOF/width scenes | Remaining exact source coverage possible; FOF0/2 and ordinary all-off paths already have representative acceptance. Not selected here. |
| FP alias e16/m8 original64-data-error history | Real unresolved original symptom, but isolated/50-call controls passed and the retained682-call full-history candidate is costly. Not replaceable by another cheap generic point. |
| NF8 original169-versus128 difference / kernel waits / ambiguous segment boundaries | Original signal/context or acceptance evidence gap; not a justified short internal reproducer. No fake Sv39 closure of Linux ABI. |
| Unknown-last-trial Gather/merge stalls and other unclosed parent histories | Not selected. No guessed exact tuple, new prefix or timeout-based bug claim. |

This is not a fresh audit of every871 failed or198 stalled ELF. The focused
deduplication uses current terminal reports and source geometry, not family
names as a substitute for exact coverage.

## Archive, Identity And Measured Failure

Let
`H=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_negative_stride_handoff01`
and `S=H/singles/rvv_small_fault_strided_negative_stride_e16_m1_u1_s0_b3_m2_f0_g3`.
The original parent is `rvv_fault_replay_strided_negative_stride_e16_m1`.
The exact independently failed executable is `S/scenario.elf`.

| File relative to H | SHA256, rechecked |
| --- | --- |
| selected single scenario.elf |4c10f89aeb0d400412b15115b48ad3f11d9296fc881fb2645e573a5807d0e907|
| selected single scenario.c |90996937a77228ac31baf0323079d97e8c5004fad163e80a950ac670b82eb563|
| selected single scenario.S |597a58a41e73941a90e3ccc015676dca606d9f6f74436b2965dede15bfab3039|
| selected single case.json |90e2325772d69fc5353e3cde71e1cb7562b62d863fd68920b562ea8b92057e41|
| evidence/single_manifest.json |dc879ed4509e0f801ceb6e15a19c519707ed258c2963d42df87a76b36fc76c2f|
| evidence/single_board_report.json |9765d4734ef678223be145e14c2f2bc4ea1458bc5f2ab3a3a49321ed185a3bf9|
| evidence/single_symptoms.json |0593af45ed3527e1d5b72033cac67b6ec6aaea554ccb792a5293577d81f235ed|
| controls/rvv_trace_fault_original_strided_negative_stride_e16_m1/scenario.elf |1bfbb55bb01dc16c4f309fdc3a23f969026912acf8819f8edbfe99fd852d4885|

The corresponding baseline-control ELF actually has the same whole-file hash
as the immutable original. Its baseline.c hash is
`631da853fe5939e2a812145d23155767d4e803f3d9aa22133187d6455905588a`.
The archived controls manifest records byte-identical reconstruction; no new
rebuild was performed here. Diffing baseline.c against the selected single
finds the exact tuple filter and BEGIN/CONTEXT/RETURN/CHECK diagnostics, not a
replacement numerical oracle. The single nevertheless correctly declares
`original_rebuild_byte_identical=false`, `single_current_oracle_trial`.
Full-sequence per-trial equivalence to the uninstrumented Linux parent is not
proved by the aggregate match. Keep these provenance limits explicit.

The actual `.results[]` entry in single_board_report.json records failed/exit1,
0.2199554997496307 board seconds, with:

```text
RVV_FAULT_BEGIN unmapped=1 store=0 boundary=3 mode=2 split=0 gap=3
RVV_FAULT_CONTEXT sig=11 code=1 address=272794079230 expected_address=272794079214 pc=68114 expected_pc=68114 vstart=3 expected_start=5 vl=8 vtype=8
RVV_FAULT_RETURN status=0 faults=1 expected_faults=1 handler_errors=1
RVV_FAULT_CHECK errors=1
RVV_FAULT_REPLAY_FAIL sew=16 cases=1 signals=1 errors=1
```

case.json preserves a different full-trace mapping/PC: address273388400638
versus273388400622, PC68134 matches its expected PC, vstart3 versus5. Do not
mix those absolute addresses with the independent single. Both have P-2
versus P-18, an address delta16, and the same wrong element coordinate.
The original and byte-identical baseline controls both report96 cases,
96 signals,64 errors/exit1. Those aggregate errors are not64 identified roots.
For this single, errors1 is fully accounted for by handler_errors1: **no
separate returned-vector data error is established**.

Read-only disassembly of the actual stripped single ELF gives capacity at
0x109f6 (three instructions), replay_0 at0x109fe (ten instructions), target
PC0x10a12=68114, encoding **09c55c07**, `vlse16.v v24,(a0),t3,v0.t`.
The original `ld t3,0(a5)` carries the signed stride; do not substitute x0 or
an immediate. Retain v24 preload, mask load, VL8 setup, immediate returned
vstart, capacity restore and complete v24 store. Store helper remains present
but uncalled. Symbols were not assumed on the stripped ELF.

## Exact Geometry And Oracle

Let M be the beginning of the original8KiB mapping and P=M+4096. The lower
page M..P-1 is unmapped; the upper page stays readable. Source equations give
base=P+22 and `address(i)=P+22-8*i`:

| Element | VA | Predicate | Required first-attempt action |
| ---: | --- | ---: | --- |
|0|P+22|0|skip|
|1|P+14|0|skip|
|2|P+6|1|load and commit prefix|
|3|P-2|0|skip, no target translation or AR|
|4|P-10|0|skip, no target translation or AR|
|5|P-18|1|load page fault, vstart5|
|6,7|P-26,P-34|0|after retry, skip and complete|

The fault handler must see cause13 in an S-mode port, target PC unchanged,
tval=P-18, VL8/vtype8/vstart5 and the committed old/prefix destination before
repair. The Linux original sees SIGSEGV/SEGV_MAPERR; that ABI is not reproduced
by substituting an M-mode observer. A correct prefix is v24[2]=0x287a and
inactive elements0/1/3/4=0x005b. Remap/refill the lower page, then poison only
completed active element2's memory at P+6 with XOR0x5b (becoming0x2821).
Retry the same target PC with vstart5; do not reload vd or re-enter helper setup.
Final v24[2] must remain0x287a, not the poisoned0x2821, and v24[5]=0x26be.
Both constants derive from the original halfword formula, not captured DUT data.

Retain all source initialization and oracle: input64 values101+13*i, offsets128
even though unused by this strided helper, output130 halfwords initialized0x5b,
mask16 bytes0x24 (capacity64 vlm consumes8 bytes), all64 result elements and
guards output[0]/output[65], and all4096 halfwords of8KiB memory. Only P+6 may
contain the specified poison after completion; all other memory follows
`uint16_t(((A-M)/2)*37+11)`. Keep one fault, returned vstart0, same-PC replay and
full handler checks. Do not call this128 result fields or128 mask bytes.

No preceding vector warmup is needed for the **independently measured single**:
its selector runs before mapping/setup. Its source-derived zero-based parent
ordinal is61, but neither execution of61 predecessors nor a claim that the
parent failed first at61 follows from that calculation.

## Current RTL And Falsifiable Probe

Relevant live files match M6 frozen/sources byte-for-byte, verified read-only:

- `hardware/src/vlsu/addrgen.sv` SHA470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da.
- `hardware/src/vlsu/vldu.sv` SHA4e46a4733530b15edb05bbaded651899511af930e2caffe77b7482528c4fc8ab.
- `hardware/src/ara_sequencer.sv` SHAbf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655.

Static path:

1. AddrGen320 forms resumed strided address from base+vstart*stride.
   memory_predicate604..633 obtains the load mask owner/window and computes
   element=`VL-(remaining_bytes>>EEW)`. For e16, remaining bytes at fault5
   must be6, not a VA-derived page offset or element3 count.
2. AddrGen924..947 emits inactive skip descriptors, decrements one element and
   adds the signed two's-complement stride. Active start_req978..980 is
   predicate gated. Descending addresses still advance the element ordinal.
   Strided load1064..1074 uses one-element AR; next address1102 adds stride.
3. MMU fault1250..1283 enqueues an exception marker after prior descriptors and
   computes exception_vstart from remaining bytes. Ordinary load has FOF=false.
4. VLDU625..666 queues the partial prefix, waits for queue occupancy0 and all
   final grants, then emits the owning done and clears byte counters. Sequencer
   989..991/1024..1029 waits for the **same load VID's** completion on a fault.

These repairs already address the observed early inactive fault and known
prefix-drain risks. Two's-complement add/multiply supports negative stride at
these widths; there is no static proof here of a missing sign extension or an
unrepaired current bug. Do not patch merely because the old single failed.

If a future separately authorized real-Sv39 run fails, a bounded target window
should distinguish, in order:

- Held request VID/op/base/stride/vstart/VL/EEW plus state acceptance; a broadcast
  valid level alone is not proof that AddrGen accepted a new instruction.
- `axi_addrgen_q.addr/len/stride`, `idx_predicate_valid/active`, load mask
  owner/first_element/valid. At element3/4 predicate must be inactive despite
  their VA lying in the absent lower page.
- `axi_addrgen_queue_push`, descriptor is_skip/is_exception/elem_start,
  valid/ready consumption, `mmu_req_o/mmu_vaddr_o/mmu_valid_i/mmu_exception_i`,
  and AR valid/ready. MMU request can remain asserted for several cycles;
  count distinct target elements/accepted transactions, not raw high cycles.
- Prefix R consumption, result BE/data, accepted VRF requests **and final
  grants**, exception FIFO/byte counters, same-VID done, ack and ara_resp.
  Correct tval but stale v24[2] implicates drain/ownership rather than masking.
- Actual fault CSR context, repaired PTE+SFENCE, unchanged target-PC retry,
  resumed base=P-18/vstart5, no second load of P+6, final vstart0/full oracle.

A false translation at P-2 recreates the old predicate/coordinate failure.
A correct translation at P-18 with wrong signed address later is a different
address/restart defect. A correct current pass would accept only this source
single, not prove the original root from timing or close the429-record family.

## Cost And Bounded Next Step

No new executable or instruction count has been measured. A later software
port may reuse the real-Sv39 extended8 fixture/observer, but must explicitly
add negative **load** and lower-page unmap/refill, not reuse its negative-store
row unchanged. Preserve source setup/whole memory checks and add observer
context/neighbor checks without claiming Linux signal-frame equivalence.

Static work is small: initial4096 halfword fills plus2048 lower-page refill,
64 output checks/two guards, and4096 memory checks whose original
logical_element search has at most8 candidates (32768 comparisons). There is
one fault and one retry. A planning envelope0.5..1.0M firmware instructions
allows roughly0.4M for that bounded search plus other loops/observer work;
this is a source-level allowance, not a compiled WCET or measured reference.
Do not infer instructions from the0.22s Linux board time.

Measured comparable M6 NF2 pilot4:1307708 retired instructions/1759.444633s,
about743.25 retires/s, per its existing independent terminal REVIEW. This gives
roughly673..1345s for the planning envelope. At the older conservative273/s
planning proxy with20% margin, the envelope is2198..4396s (37..73min).
The different fixture, memory/exception mix and initialization prevent a runtime
guarantee. Confirm actual compiled cost with a separately authorized bounded
reference before any DUT admission; do not expand timeouts or trim the oracle.

Recommended next action is **one source-faithful single preparation**, not a
40-case negative-stride matrix or original96 Linux replay. This note itself
authorizes no preparation, reference, simulation or RTL change.

Coverage/cost evidence read here:
`masked_translation/sv39_extended/REFERENCE_REPORT.md` (explicitly excludes
negative-stride loads) and
`masked_translation/segment_review/nf2_remaining4_terminal_audit01/terminal01/REVIEW.md`.
The latter SHA is a69069028661e2263f7b1d4ac7b0ccea55b65cd6e987add0800aad9ed69a40d2.
