# e8/mf2 Full4095 Source And Preparation Review

2026-10-14. Decision: **NO_BLOCKER_FOR_HOST_AND_COMPILE_PREPARATION**.
This is a static review, not Host/reference/DUT acceptance or launch permission.
No tests, compilation, reference execution, simulator queries, large-trace reads,
RTL edits or producer-file edits were performed by this reviewer. Aquinas owns
full_e8_mf2_packed_prepare01; findings and the final code-bound verdict were sent
directly to that owner. Only this independent report is new.

## Finding Resolved Before Preparation

The initial PLAN formula incorrectly said21 ordinary and4 special operations.
Actual operations.h and original C define20 ordinary (op0..18 and24), with3
starts each, plus5 special (op19..23), with1 start each. The corrected plan and
model retain3 seeds *7 lengths *3 modes *(20*3+5) =4095 calls, not4221.
The owner also clarified tail2 and mask-load scope, and added a dedicated
low-tail-byte mutation. These are preparation corrections, not RTL findings.

## Original Identity And Sequence

Archive root: /home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04.
Original Linux ELF: overlay/opt/ara-tests/rvv_matrix_e8_mf2.
Its freshly read SHA equals recovery22/rvv_matrix_e8_mf2:
`2e16fe0a09238c14efb89b28326190c15225b10680138e7339f07c8541f38093`.
recovery22/report.json records exact_elf_equal and disassembly_equal true.
The original C bytes are not recovered; reconstructed_oracle.c is the
binary-equivalent reconstruction, SHA
`7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91`.

Original assembly rvv_matrix_e8_mf2.S SHA
`49e955479c7c53ffd5b58e94552afd2abf17f23572c36ee7cb810b68a5bd795b`;
e8/operations.h SHA
`7686eb17f96d500c82711d09bbaa74c965352b4257b0b7db3510d3fbbd9bf48c`.
Read the existing original.dis, not a simulated trace: capacity at10856 has
three instructions, including0072f557; op0 starts1085e, target1087c/00880c57.
Each opN starts1085e+0x30*N, contains13 instructions through ret, with target
at start+0x1e. All25 helpers retain the source setup/load/mask/vstart/target/
vstart-readback/full-capacity-store sequence. New linked addresses cannot be
borrowed from these original Linux PCs.

The new model independently follows reconstructed C seed/op/length/mode/start
order, with lengths0,1,2,3,32,63,64 and duplicate starts preserved. RNG resets
only at each seed and advances64 times with the original xorshift and special
values. It does not trim another shape's expected output. Relevant checks:
- op21 uses CAP64 OOR: b[2]=255 produces0, unlike CAP512.
- op20 reads a[i+2] only below64; its final two all-active outputs are0.
- op22 retains b[0] seed and modulo256 selected reduction; op23 retains stable
  compression and sentinel suffix. All five special operations retain start0.
- Modes remain all-selected, odd indices, and i%7==2; no invented fourth mode.
  Input arrays1024 each, output1026 and mask128 bytes remain allocated.

Full scope is262080 result bytes,8190 guards,4095 returned-vstart checks and
53235 helper instructions, plus the one3-instruction capacity call. Original
source has no explicit fflags oracle; no additional flag coverage is claimed.
No prefix exit, call deduplication, partition reset or vector warmup is added.

## Fractional Layout And Exact Footprint

At VLEN1024/e8/mf2, VLMAX=64. v8/v16/v24 each refer to a fractional group
within one physical128-byte register, not two fractional groups sharing a
software register name and not an m2 group. Original setup and store observe
only64 bytes of each named vector register. The unused physical upper64 bytes
are not initialized or checked by this source helper; do not add an extra RVV
probe or claim full-physical-register coverage.

The full software mask128 is retained, with8 meaningful bytes and120 zero
bytes. Original vlm executes at capacity64 and reads8 bytes; this does not
load all128 bytes into v0. Mask initialization remains once per mode before
the start-trial loop, not moved into each trial or across helper calls.

Actual output span is out[0..65], with destination out+1:
- raw offsets0..63: first guard plus results0..62, covered by8 complete words.
- raw offset64: result63, the low byte of tail2.
- raw offset65: rear guard, the high byte of tail2.

packed.h uses byte-pointer builtin memcpy, eight8-byte accesses and one2-byte
access, avoiding a misaligned uint64_t cast at out+1. expected_words[4095][9]
has294840 ROM bytes; padding in the ninth ROM word must never cause an8-byte
output access at offset64. Source initialization/comparison stop at66, leaving
out[66..1025] untouched. Original fallback checks every result and both guards
on mismatch; successful packed comparison only advances elements by64.
The vstart-return check remains outside that fast path and is not suppressed.

## Host And Compile Gates Reviewed

prepare.py preserves original C fallback verbatim and the original loop/RNG
body through the existing runtime_adapt; only scalar output initialization,
mask copy and successful comparison are replaced, with cap==64 enforced.
Host uses both actual C loops, original C value/selected expectations against
the separately generated Python table, every input/mask byte, fresh output
and unused backing zeros. It retains whole4095 even in negative runs.

Host plan covers active/prestart/inactive/tail/frontguard/rearguard, a nonzero
64-bit returned-vstart, and explicit out[64] corruption. It also mutates every
one of66 bytes in the packed primitive, checks unaligned copies, and places
the66-byte span immediately before a protected page. Original and packed
diagnostics/counters must match. UBSan trap calibration is distinct from a
numerical negative. This code review does not assert those tests have run.

Compile plan uses existing toolchain/runtime, -O2 with both vectorizers disabled,
separate unchanged .S helpers, exact unique original-ELF helper-byte matches,
and an executable instruction scan rejecting extra RVV outside capacity/op
windows. Both SoC and Spike backends must pass. The1MiB link script and actual
BSS/stack gap enforce64KiB reserve;294840+384 bytes of ROM alone is not a full
link/stack proof. Source memcpy count is not proof of actual8 LD/SD +LHU/SH;
inspect actual compiler output and the tail access width before final acceptance.

No reference dispatch is present in prepare.py. Its proposed one-attempt
3M-instruction/120s/768MiB reference bounds are not measured runtime or a VCS
budget guarantee. A separate review of actual artifacts and the full reference
checker is still needed: all4095 owner/helper windows, full data/CSR and source
history, unrelated-helper/RVV rejection, backend-specific completion, numeric
wait receipts, transitive module identities and a measured <=3h cost basis.
Passing a short prefix or a different accepted shape does not satisfy this.

## Reviewed Preparation Identity

The following code snapshot was read, not executed. Files remain producer-owned;
later code changes require a delta review rather than silently inheriting this
verdict. No generated ELF or final READY is accepted by this table.

| File in full_e8_mf2_packed_prepare01 | SHA256 |
| --- | --- |
| PLAN.md | e944feef769994af7d5e9b6c61900fd6c71cc4d8a06c650090b0e93d9cc271fe |
| prepare.py | 7eacf48a5c52e4103fb3ea2f3c13406e0e65fc3f6837d4f1e0c5c3eb6cdc41dc |
| model.py | 66abb0a8824616530e188b34634ade72416f87c6359a8dd7094b492e40a04019 |
| host.c | dcf422490059ab28211e36ac92d42fa8da7fa292ab7447baafbf19925f4d3cf8 |
| packed.h | 9b7fb8f17353f1d3d4046864d96d79be628ab7e90f394bbfaebb767348cbce90 |

Mechanism references read: full_e8_m4_dict_prepare01/{model.py,packed.h,host.c,
prepare.py}, full_e8_m8_block_unrolled01/packed.h, and the imported
full_e16_mf4_prepare01/model.py and prepare.py plus original runtime_adapt.
Only scalar packing mechanics are reused; CAP-specific gold, group layout,
input length, helper identity and acceptance scope are not inherited.
