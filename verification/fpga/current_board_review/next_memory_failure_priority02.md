# Next Memory Failure: Negative-Stride Store

Static selection only, 2026-10-12. No DUT/reference/compiler/build, live-job
query, RTL change or large raw-log scan. Existing metadata, source and small
board reports were read. **One proposal only:**

`rvv_small_fault_strided_negative_stride_e16_m1_u1_s1_b3_m2_f0_g3`

This independently board-failed source single has an exact tuple and complete
oracle, needs no predecessor/warmup, and is not the accepted M6 negative-load
single. Its descending sparse store, lower-page unmap/refill, precise store
fault, committed-prefix poison and retry exercise a different consumer path.
**No still-unfixed M6 root cause is proved.** The observed historical early
fault is consistent with the repaired predicate path; the proposed test would
falsify that repair for this exact store and check store completion separately.

## Bounded Inventory And Deduplication

Let `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01` and
`G=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review`.
CURRENT_SCOPE inspected SHA256:
`795520db23297acee0c6d1541f6716f55339db425f9d4339d71f463890bbfb6e`.
This is a review of collected exact-source inventories, not a new census or
closure count for all429 historical replay records.

| Collected source records | Exact current-M6 status and disposition |
| --- | --- |
| Negative stride e16/m1,40 independently failed singles in `C/rvv_negative_stride_handoff01/evidence/single_manifest.json` | Only `u1_s0_b3_m2_f0_g3` has exact M6 acceptance in the reviewed ledger. Other39 remain outside that acceptance. Select the corresponding **store** once, not another load. |
| Unit-stride e16/m1,20 singles in `C/rvv_fault_handoff_e16m1_01/evidence/single_manifest.json` | M2 H/I contain selected ordinary/all-off and load/store cases; no exact current-M6 replay of those source singles was identified. Lower priority than the descending store/remap path. |
| Protected-page/FOF,20 reduced singles in `C/rvv_small_exceptions01/manifest.json` | M6 e8/scenario0 and e64/scenario5 accepted; other18 are not accepted by those runs. M2 e16 scenario0/2/3 coverage remains M2. Do not repeat the accepted pair or conflate these20 with eight parent/detail ELF records. |
| NF8 positive-stride e32/mf2,192 source-derived tuples | Full192 independently accepted on M4, not M6. The unresolved169-versus128 original difference is Linux signal/context/history, not a recovered new Sv39 failing tuple. Repeating a passed Sv39 point would not explain it. |
| NF2 exact40 failed-single geometries and NF7 source96 | Current M6 independently accepted, per latest ledger. Excluded; two additional J4 positive controls are not failed records. |
| Indexed overlap source programs | Three source-faithful M6 programs accepted after the measured mixed-EEW repair. Excluded from this selection. |
| Kernel waits, ambiguous segment stalls, Gather11 | Missing exact trigger/phase or acceptance evidence. Not replaced by synthetic small cases or guessed prefixes. |

Exact compact enumeration of the negative40 is
`u in {0,1}, s in {0,1}, (b,m) in {(1,2),(1,3),(3,2),(3,3),(5,3)}, f=0,
g in {1,3}`. Remove only `(1,0,3,2,0,3)` for the accepted M6 load:39 remain.
The unit20 use the same set without g. The exception20 are
SEW in8/16/32/64 x scenario0/1/2/3/5, minus the two M6 selections above.
These enumerations identify records, not distinct roots or run proposals.

Reuse these existing scope/acceptance documents, not their old pending prose:
`G/masked_translation/negative_stride_load_vcs_m6_plan01/terminal_waiter01/TERMINAL_REPORT.md`,
`G/masked_translation/fof_two_singles_vcs_m6_plan01/terminal_waiter01/TERMINAL_REPORT.md`,
`G/masked_translation/nf8_strided_review/nf8_remaining_scope_review01.md`,
and latest CURRENT_SCOPE NF2/NF7 terminal entries. The NF8 Linux prefix13
diagnostic is a different environment and is not selected here.

## Original Identity And Actual Failure

`H=C/rvv_negative_stride_handoff01`;
`S=H/singles/rvv_small_fault_strided_negative_stride_e16_m1_u1_s1_b3_m2_f0_g3`.

| Actual file | SHA256 rechecked |
| --- | --- |
| S/scenario.elf | `07d285218316422ea69480c764c09fe17e7ebca6a49e31c5abc7e4ff6cae5578` |
| S/scenario.c | `5ece6a9e216d611b4b62823d037b9b3f35304b952fb693375b86e8d79d023c4d` |
| S/scenario.S | `597a58a41e73941a90e3ccc015676dca606d9f6f74436b2965dede15bfab3039` |
| S/case.json | `13cc8acb9c6d118654aae7653001ea07baf336c541d937726632f230f2278117` |
| H/evidence/single_manifest.json | `dc879ed4509e0f801ceb6e15a19c519707ed258c2963d42df87a76b36fc76c2f` |
| H/evidence/single_board_report.json | `9765d4734ef678223be145e14c2f2bc4ea1458bc5f2ab3a3a49321ed185a3bf9` |
| H/evidence/single_symptoms.json | `0593af45ed3527e1d5b72033cac67b6ec6aaea554ccb792a5293577d81f235ed` |

The exact `.results[]` entry in single_board_report records exit1,
0.4223403004 board seconds:

```text
RVV_FAULT_BEGIN unmapped=1 store=1 boundary=3 mode=2 split=0 gap=3
RVV_FAULT_CONTEXT sig=11 code=1 address=272892628990 expected_address=272892628974 pc=68156 expected_pc=68156 vstart=3 expected_start=5 vl=8 vtype=8
RVV_FAULT_RETURN status=0 faults=1 expected_faults=1 handler_errors=1
RVV_FAULT_CHECK errors=1
RVV_FAULT_REPLAY_FAIL sew=16 cases=1 signals=1 errors=1
```

Actual ELF PT_LOAD bytes at PC68156 (`0x10a3c`) are **09c55c27**,
`vsse16.v v24,(a0),t3,v0.t`. The original store helper has ten instructions,
including source preload, `ld t3,0(a5)`, mask load, VL8 setup, target, returned
vstart, capacity restore and full v24 output store. Capacity has three
instructions; retain the unused load helper but do not execute it.

case.json/full-sequence trace uses PC68172 and different mapping addresses;
do not mix those addresses with this independent single. Both observations
have actualP-2 versus expectedP-18, delta16, actualvstart3 versus5.
Errors1 is accounted for by handler_errors1: **no separate returned-data
failure was measured in this log**.

Parent name is `rvv_fault_replay_strided_negative_stride_e16_m1`, immutable
ELF SHA `1bfbb55bb01dc16c4f309fdc3a23f969026912acf8819f8edbfe99fd852d4885`.
The archive labels the selected executable `single_current_oracle_trial`,
not a byte-identical parent ELF; original per-trial equivalence to the old
aggregate remains unproven. The measured independent single itself is real.
Its selector executes before mapping/setup, so no preceding target calls are
needed to reproduce that single scope. Do not claim a full96 parent replay.

## Geometry And Complete Oracle

NF1, e16/m1/tu/mu, VL8, initial vstart0; cap64 on M6 VLEN1024.
For an8KiB mapping beginning M, P=M+4096. Lower page is unmapped;
base=P+22, stride=-8, all16 mask bytes0x24. Target addresses are:

| Element | Address | Active | Expected first attempt |
| ---: | --- | ---: | --- |
| 0/1 | P+22/P+14 | no | skip |
| 2 | P+6 | yes | store input[2]=127, committed before fault observation |
| 3/4 | P-2/P-10 | no | skip, not a page fault or data write |
| 5 | P-18 | yes | store page fault, vstart5 |
| 6/7 | P-26/P-34 | no | skip after same-PC retry |

Preserve all original setup: physical input128 with first64 initialized
`101+13*i`, all128 unused offsets, output130 halfwords initialized0x5b,
mask16 bytes, and full4096-halfword memory formula
`uint16_t(((address-M)/2)*37+11)`. Original helper passes output+1 and cap64.
Source handler requires the unchanged target PC, SIGSEGV/SEGV_MAPERR,
VL8/vtype8/vstart5, saved source v24[0..4] and the completed active store.
A real Sv39 derivative would check cause15/P-18 and architectural CSR state;
that is not Linux signal-frame equivalence.

Remap/refill all2048 lower-page halfwords, then poison completed element2:
memory[P+6] becomes `input[2] ^ 0x5b = 0x24`. Retry **the same target PC** with
vstart5, original a0=P+22 and t3=-8; never adjust a0 as well as vstart and
never re-enter helper setup. Final memory[P+6] must remain0x24 and
memory[P-18] must equal input[5]=166. Every other halfword must retain the
source memory formula. Output[1..64] equals all64 source input values,
including nonactive and tail source elements; store does not alter v24.
Original guards are output[0]/output[65], not output[129]. Require exactly
one fault and returned vstart0. Extra physical-output/page-table/neighbor
checks may strengthen observation but must be labelled supplemental.

## Why This Is Not A Duplicate

The M6 load at exactly the corresponding geometry checks VLDU data/final
grants, not W strobes, pending B ownership, or store side effects. Its source
helper is09c55c07, not this09c55c27. M2 extended8's `negative_store_retry`
is **u0/s1/b3/m2/f0/g1**, baseP+10, stride-4, permission repair rather than
unmap/refill. Its original mapping is documented in
`G/masked_translation/sv39_extended/REFERENCE_REPORT.md:21` and its actual
configuration in `fixture.h`. Neither is exact current-M6 acceptance of this
selected single. NF2/NF8 segment stores have different NF/geometry/source
oracles. Their acceptance is relevant confidence, not source-identity closure.

## Falsifiable Hypothesis And Existing Repairs

Read-only hash comparison found current AddrGen, VSTU and sequencer identical
to frozen M6. AddrGen SHA470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da;
VSTU SHA139b27c0784c867b7a6032665c1634bb4b843ec2d9be5c4a3c6cb6d8fd2919f2.

Historical hypothesis: element3 was translated without its inactive predicate,
producing P-2/vstart3. Current AddrGen:604..633 selects the store mask's owner
and element window; inactive descriptors skip translation at924 onward.
Thus this root appears **covered by existing code**, not statically still
present. If the selected program recreates P-2, the falsifier is the same
target VID's element3 predicate/owner/skip versus actual MMU request.

Distinct store hypothesis: descriptor skips or nonzero-start resumption could
misalign store data, or expose the fault before the earlier active store is
complete. VSTU:384 permits skip consumption without W readiness;454 suppresses
W for skip;460 increments pending B only for real WLAST;530 consumes B for
the owning slot;578 waits for pending B zero before fault cleanup. Sequencer
uses same-store completion when WaitForStoreB applies. These are present
repairs, so **no new bug is asserted from a stale TODO or an old failure**.

Discriminators for a later separately authorized failure investigation:

- Bind target PC/VID, accepted request, base/stride/VL/vstart and store mask
  owner/first-element. At elements3/4, correct skips must not create target
  MMU/AW/W transactions or pending B entries.
- Count accepted AW/WLAST/B with owner slot and descriptor elem_start;
  distinguish skipped descriptors from real bursts and valid levels from
  handshakes. Prefix memory[P+6]=127 must be visible at fault observation.
- Fault must report P-18/start5, not P-2/start3. Correct metadata with stale
  prefix memory instead implicates store drain/completion ordering.
- After unchanged-PC retry, W data for element5 must be166; final P+6=0x24
  distinguishes proper restart from replaying the committed store with127.
  Full8KiB checks distinguish wrong data ordinal/strobes from correct context.

No bounded run can guarantee a specific B latency; do not claim arbitrary
backpressure coverage or force internal state. Start with the actual source
oracle, not a new synthetic bus test.

## Reusable Fixture, Reference Gap And Cost

Existing read-only bases:
`G/masked_translation/negative_stride_load_original01` provides the exact
descending unmap/refill geometry, real Sv39 observer, full setup/memory and
same-PC context checks. `G/masked_translation/sv39_extended/{fixture.c,fixture.h,fixture.S,reference.py}`
provides the store source/prefix/poison behavior. Neither sealed checker may
simply be relabelled: the load checker rejects the store-helper range, and
extended8 uses different geometry. A future **new owned** adapter must retain
the selected original10-instruction helper and this source's full oracle.

There is **no claimed exact new store SoC ELF/Spike reference**. The adjacent
M6 load's actual reference is836971 firmware instructions; its DUT took
996.679668s, with17274 checks/four memory checkpoints. The selected store has
the same4096 initial memory words,2048 refill words,64 results/two guards and
at most4096*8 original memory-oracle address comparisons; source-save and
poison handling differ. A planning allowance0.85..1.10M instructions is
reasonable but not a compiled bound. At273 retired/s plus20%, it is
3736..4835s, about62..81min. A prospective1.5M reference ceiling would imply
about110min by the same proxy, below3h, not a runtime promise or authorization.
Do not infer VCS time from the0.422s original Linux result.

Recommended next action, only after review: prepare this one authentic
source single in a new directory, prove the compiled cost before any bounded
reference, and preserve all oracle/initialization/context. No batch39, no
full96/Linux replay, no repeated accepted M6 load/FOF/NF2 tests. This note
authorizes no execution or RTL change.
