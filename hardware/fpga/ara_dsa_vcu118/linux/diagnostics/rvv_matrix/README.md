# RVV Hardware Matrix

These are userspace instruction oracles for the unchanged FPGA image. They
are not an exhaustive ISA certification. Each ELF is independently bounded;
ordinary numerical mismatches are accumulated, with at most twenty detailed
examples printed, rather than ending the shape at its first mismatch.
Illegal instructions or kernel stalls still require scene preservation.

## Original Matrix Coverage

- All 22 legal SEW/LMUL shapes for ELEN=64: SEW 8/16/32/64, fractional LMUL
  where legal, and LMUL 1/2/4/8. Capacity is read at runtime.
- Seven VL points including zero, one, small values, half capacity and both
  upper boundaries. Three mask patterns: all-on, alternating, sparse.
- Three reproducible input seeds including zero, all-ones, signed minimum,
  signed overflow division, zero divisors and out-of-range shift amounts.
- Integer add/subtract, logic, signed/unsigned min/max, shifts, multiply,
  signed/unsigned division and remainder in vector-vector form. This
  original matrix adds scalar/immediate forms of add, not every arithmetic
  form. Later fixed-point and comparison releases have their own form coverage.
- Slide up/down, gather, masked sum reduction and compression.
- Masked unit-stride loads and unmasked output stores.
- FP32/FP64 add/subtract/multiply/divide/min/max, sign injection and square
  root. Expected bits are generated on the host from small dyadic fixtures,
  not from the FPGA scalar floating-point unit. Includes signed zero,
  divide-by-zero infinity and invalid-operation canonical NaN results.
- Tail/masked-off sentinels, pre-vstart preservation, post-instruction
  vstart=0 and memory guards. Nonzero vstart is only exercised where legal;
  reduction and compression use vstart=0. Values outside the representable
  vstart range are not misclassified as legal restart tests.
- Current destination-policy checks use tu/mu. ta/ma must allow either the
  old value or all-ones in agnostic elements, not require one particular
  implementation choice. They are not covered by the original release;
  the extension below adds ta/ma tests.

The 22-ELF matrix has 107,100 checked execution configurations when all
complete. These are combinations inside 22 binaries, not 107,100 independent
processes. The log additionally reports actual checked element counts.
Some repeated small-VL boundaries may coincide at small capacities.

## Coverage Additions

Integer multiply-add source aliases can be generated with
`integer_forms.py --multiply-add --accumulators --alias-source first`,
`second` or `both`; add `--unmasked` for unpredicated execution. They
cover exact full-group overlap at vstart=0, not partial-group overlap,
restart or multi-instruction dependency chains. The five accumulator
patterns are also the aliased source inputs. All inactive logical
elements and surrounding memory guards retain their old values.

The 20261009 dual-DDR campaign adds 2752 coverage ELFs plus fifteen
focused diagnostic ELFs, all reference-validated.
Both VLEN512 and VLEN1024 references pass. Board results are tracked separately:

| Batch | Families | ELFs | VLEN1024 Configurations | Board State |
| --- | --- | ---: | ---: | --- |
| additions03 | Integer extension, tu/mu and ta/ma | 44 | 221760 | All passed |
| additions04 | Masks, resident memory, width changes | 59 | 129840 | All passed |
| additions05 | FP, whole-register, signal context, FOF | 15 | 50786 | 10 passed, 5 failed; all executed |
| additions06 | Fractional/sticky fixed point, reductions | 54 | 81480 | 53 passed, 1 failed; all executed |
| additions07 | Detailed whole-move and fault reproduction | 5 | 1518 | All five reproduced failures; all executed |
| additions08 | Extension/overlap, RTZ/class, NF3..8 segments | 66 | 104328 | 3 passed, 1 confirmed stall; 62 pending in preserved continuation |
| additions09 | FP16 arithmetic/conversions/class, FP32/64 width/ROD | 10 | 45360 | All passed in recovery05 |
| additions10 | Independent index EEW and ordered duplicate stores | 22 | 32760 | All passed in recovery05 |
| additions11 | FP16/32 widening/narrowing and ROD | 5 | 6300 | All passed in recovery05 |
| additions12 | Scalar/immediate mask comparisons and mask-logic aliases | 44 | 51744 | All passed in recovery05 live04 |
| additions13 | Ordered/unordered indexed NF2..8 segments | 17 | 28560 | All passed in recovery05 live04 |
| additions14 | Nested alternate-stack signals and misaligned segments | 10 | 59728 | 1 passed, 9 preparation traps; CAP-01 |
| additions15 | Special FP16/32/64 ordered sum/min/max reductions | 15 | 100800 | 4 FP64 passed, 11 FP16/32 failed; RVV-07 |
| additions16 | FP16/32/64 scalar arithmetic/FMA and NaN boxing | 15 | 50400 | All passed in recovery05 |
| additions17 | Fixed-point scalar/immediate rounding and saturation | 22 | 221760 | All passed in recovery05 |
| additions18 | Scalar FP reverse/min/max/sign and invalid NaN boxing | 26 | 127400 | All passed in recovery06 live02 |
| additions19 | Masked comparison destinations alias either source | 22 | 22176 | All passed in recovery06 live02 |
| additions20 | Destructive-multiplicand FP16/32/64 FMA, vv/vf | 30 | 50400 | All passed in recovery06 live02 |
| additions21 | Integer scalar logic/shift/min/max/multiply/divide | 22 | 64680 | All passed in recovery06 live03 |
| additions22 | Integer multiply-add/subtract, vv/vx | 22 | 24640 | All passed in recovery06 live03 |
| additions23 | Integer arithmetic/logic/shift immediate boundaries | 22 | 29568 | All passed in recovery06 live04 |
| additions24 | Unmasked integer scalar, multiply-add and immediate forms | 66 | 118888 | All passed in recovery06 live07 |
| additions25 | Carry/borrow data and packed-mask results, all operand forms | 44 | 40656 | All passed in recovery06 terminal report |
| additions26 | Merge/move, gather vv/vx/vi/ei16, slide vx/vi and slide1 | 22 | 309792 | 19 passed, 3 failed in recovery07; RVV-08 |
| additions27 | Integer multiply-add/subtract old-destination patterns, masked/unmasked | 44 | 246400 | All passed in recovery07 |
| additions28 | FP16/32/64 packed comparisons vv/vf, NaNs and sticky flags | 15 | 268800 | All 15 failed in recovery07; RVV-09 |
| additions29 | FP merge/broadcast, masked/unmasked slide1, scalar/vector moves and boxing | 15 | 559104 | All passed in recovery07 live10 |
| additions30 | Unmasked FP comparisons and destinations aliasing v8/v16/v0 | 60 | 1075200 | All60 failed in recovery07 live14; RVV-09 |
| additions31 | FP move/merge/slide1 nonzero restart and scalar transfer boundary rules | 15 | 2236416 | 1 failed,1 stalled,13 pending in recovery07 terminal; RVV-10 |
| additions32 | Target-only alignment capability diagnostics, NF3..8 unit/strided segments | 9 diagnostic | 3816 child scenarios | Reference passed; queued after additions31 |
| additions33 | Fixed-point vv/vx/vi nonzero restart, rounding and sticky saturation | 44 | 1123584 | Both references passed; remaining cases included in recovery08 |
| additions34 | Masked/unmasked FP comparison restart, packed prestart bits and flag suppression | 30 | 2150400 | Both references passed; included in recovery08 |
| additions35 | Integer vx/vi comparison restart and both vector-source destination aliases | 44 | 177408 | Both references passed; included in recovery08 |
| additions36 | Permutation restart and mask-logic source-alias restart | 44 | 1357440 | Both references passed; included in recovery08 |
| additions37 | Resident aligned unit/stride/indexed/NF2 memory restart | 22 | 87264 | All22 board cases passed across recovery14/15; exact-ELF audit complete |
| additions38 | NF3..8 unit/stride and NF2..8 EEW32 indexed segment restart | 31 | 251328 | All31 board cases passed; exact-ELF reference audit complete |
| additions39 | Independent index EEW8/16/32/64 restart and ordered duplicate stores | 22 | 131040 | All22 board cases passed; exact-ELF reference audit complete |
| additions40 | NF2..8 indexed segment restart with independent EEW8/16/64 | 51 | 340032 | All51 board cases passed; exact-ELF reference audit complete |
| additions41 | Integer multiply-add/subtract source/destination aliases, masked/unmasked | 132 | 492800 | All132 board cases passed across recovery14/15; exact-ELF audit complete |
| additions42 | Integer multiply-add restart, disjoint and first/second/both source aliases | 176 | 2956800 | All88 unmasked ELFs passed; masked subgroups incomplete with recorded stalls |
| additions43 | FP16/mf4 slide restart failure classification | 1 diagnostic | 172032 | Executed; prestart element clobber reproduced in recovery08 live01 |
| additions44 | Three-instruction repeated/mixed multiply-add dependency chains and exact source aliases | 352 | 1478400 | All352 board ELFs passed; exact-ELF legacy-manifest/reference audit complete |
| additions45 | Unmasked FP comparison destinations aliasing v8/v16/v0 | 45 | 806400 | All 45 board cases failed; both references passed |
| additions46 | Invalid FP16/32 scalar boxes, masked/unmasked and destination aliases | 88 | 1576960 | All 88 board cases failed; both references passed |
| additions47 | Unit-stride load/store page-fault signal-frame replay | 4 | 192 | All 4 board cases failed; both references passed |
| additions48 | Ordered indexed page-fault replay with permuted same-EEW indices | 4 | 192 | All 4 board cases passed |
| additions49 | Ordered indexed page-fault replay with independent index EEWs | 12 | 576 | All 12 board cases passed |
| additions50 | Unit-stride and same-EEW ordered indexed page-fault replay at non-m1 LMULs | 36 | 1728 | 18 indexed cases passed; 18 unit-stride cases failed |
| additions51 | Ordered indexed page-fault replay across non-m1 independent index EEWs | 44 | 2112 | All 44 board cases passed |
| additions52 | Unit-stride NF2..8 m1 segment page-fault replay, including within-segment page splits | 28 | 2688 | All 28 board cases failed; both references passed |
| additions53 | Unit-stride NF2..8 segment page-fault replay at all other legal LMUL shapes | 58 | 5568 | All 58 board cases failed; both references passed |
| additions54 | Positive strided NF1..8 page-fault replay at all legal SEW/LMUL shapes | 108 | 18624 | All 108 board cases failed; both references passed |
| additions55 | Negative strided NF1..8 page-fault replay at all legal SEW/LMUL shapes | 108 | 18624 | All 108 board cases failed; both references passed |
| additions56 | Ordered indexed NF2..8 segment faults, all legal independent index widths/LMULs | 338 | 32384 | 337 board cases passed; NF7/e32/mf2 same-width case failed (RVV-15) |
| additions57 | Zero-stride NF1..8 protected/absent page replay, uniform duplicate stores | 108 | 3104 | Both references passed; board execution pending |

Closed-batch board pass counts comprise 166 ELFs and 481508 configurations.
Six failing coverage ELFs and five failing diagnostic reproductions are
excluded from those pass counts. Counts for
pending rows are reference counts, not hardware acceptance. Evidence is under
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions03..48`;
Windows batch directories use `D:\fpga_runs\ara_rvv_additions_20261009_03..16`.
The partial additions08 contributes three further passes/504 configurations;
its stalled ELF does not count as a pass or a completed configuration suite.

### Recovery08 and Restart Supplement

Additions42 contains176 built integer multiply-add restart ELFs,
2956800 configurations per reference VLEN. Both masked/unmasked variants
cover disjoint groups and exact first/second/both source aliases, with five
old-destination patterns. Four representable start boundaries preserve
prestart, tail and mask-inactive elements and check cleared completion
vstart. The28 drained trace lines per ELF use only accumulator pattern0;
the other four patterns still undergo full numerical checking.
Independent reference validation finished successfully under
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/macc_restart_reference42_state.json`.
All176 are included in the reference-validated total above, not a board
pass count. Recovery07 terminated with78 passes,79 numerical failures,
one confirmed retirement stall and121 unattempted cases. Its raw UART,
debug snapshots and report are preserved in `rvv_recovery08_07/terminal_scene`.
Recovery08 combines those121 with553 reference-validated queued tests;
none of the158 prior attempts is repeated. The674-test overlay runs the
single classification diagnostic first, followed by additions34..42 and
then the remaining old cases. Former standalone tasks34..41 and43 are
disabled to prevent duplicate execution and COM6 conflicts. The unchanged
bitstream/kernel recovery uses the same validated base image and modifies
only the test rootfs overlay and equal-size embedded DTB initrd bound.
Recovery08 successfully boots to the Linux init marker. The first saved
live01 snapshot has three numerical failures (classification diagnostic
and the first two FP comparison restart shapes); the observer is live at
`rvv_fp_compare_restart_e16_m1`. These do not stop the remaining cases.
Its terminal report later records six failures and one confirmed stall,
with667 unattempted cases. Recovery09 retains that exact remaining set,
moving only the37 FP comparison/move restart cases to the tail after
repeated confirmed stalls in those families. This is execution-order
prioritization, not a skip, a pass or a reduced acceptance scope.
Recovery09 subsequently completes five integer scalar/immediate comparison
restart ELFs with numerical failures and stalls on e8/m4 at VL512/start256.
Its two no-retirement snapshots and full scene are preserved; RVV-12 records
the exact ELF/PC evidence without assuming the internal cause. Recovery10
adds all352 reference-validated dependency-chain ELFs to the661 unattempted
cases, retaining1013 cases in total. Remaining scalar-comparison and FP
comparison/move restart cases are deferred to the tail, not omitted.

### Reference-Validated Dependency-Chain Supplement

Additions44 contains352 integer multiply-add chain ELFs,
1478400 configurations per VLEN. Each configuration executes three adjacent
target instructions without target reload, CSR read or intermediate store.
Both homogeneous repeats and cyclic vmacc/vnmsac/vmadd/vnmsub chains cover
disjoint and exact first/second/both source aliases, masked/unmasked forms,
all22 legal integer shapes and five initial destination patterns.
Use `--multiply-add --accumulators --chain-steps 3`, optionally
`--mixed-chain`, `--alias-source first|second|both` and `--unmasked`.
This is vstart=0; combining chains with restart is rejected. The scalar
oracle applies each step modulo SEW, feeding its old-destination result
into each aliased source afresh. Final logical results, inactive/tail
elements, memory guards and completion vstart are checked. Intermediate
results are not separately sampled, and arbitrary opcode transitions,
partial-group aliases or changed predicates between steps are not covered.
The independent build/reference job under `macc_chain_reference44_state.json`
finished all16 source releases. Both VLEN512/1024 pass all352 ELFs and
1478400 configurations each. Reference report identities, unique pass markers,
zero exits and source/combined ELF hashes were checked before release.
They are included in the reference-passed total, not a board pass count;
board execution must follow the current campaign without interrupting it.
RVV-01 through RVV-12 findings stay open. Focused diagnostics
repeat cases for attribution; they do not add independent instruction coverage.

### Invalid Scalar Boxing Supplement

Additions46 passes both independent reference VLENs:88 FP16/32 comparison
ELFs combine invalid scalar NaN boxes with masked/unmasked encodings and
v24/v8/v16/v0 destinations. `fp_comparisons.py --unboxed` loads unsigned
low16/32 bits and transfers all64 bits using fmv.d.x, deliberately leaving
upper bits zero. Scalar comparison expectations use the existing quiet-NaN
SoftFloat entries; vector-vector comparisons retain their original inputs.
Its1576960 configurations per VLEN include946176 invalid-box scalar
comparisons and630784 vector-vector regression configurations. Reference
identities, hashes, markers and zero exits are verified. The88 ELFs are
included in the reference total; board acceptance remains pending.
This does not cover every malformed box or restart-plus-alias combinations.

### Actual Page-Fault Replay

Additions47 contains four unit-stride m1 load/store ELFs for SEW8/16/32/64.
Each executes48 cases: PROT_NONE/unmapped pages, fault boundaries1/3/5,
all/alternating/sparse/off masks and load/store. SIGINFO checks the exact
instruction PC, si_addr/si_code and saved vector vstart/vl/vtype. Completed
prefix loads/register contents and stores are checked before page repair.
The handler changes completed prefix memory, then returns without advancing
PC or changing saved vstart/data, so a wrong restart from element0 corrupts
the expected result. The complete page pair, output tails and guards are
checked after completion. Both reference VLENs pass192 cases and144 actual
fault signals. Indexed/segment replay, other LMULs and arbitrary boundaries
remain gaps. TEST-07 records the corrected prototype handler bug; failed
prototype and negative-control artifacts are not coverage passes.
Clearing the saved vstart in the separate negative-control release produces
56 numerical errors per ELF at both VLENs, with all48 cases/36 faults still
executed. This verifies the restart detector; controls are never queued.

Additions48 extends the same signal-frame oracle to ordered indexed
load/store at all four SEWs, m1 and matching index EEW. Cyclic index
permutations stay separately within the accessible prefix and faulting
suffix, but change physical address ordering. Exact si_addr uses the index,
while saved vstart and poisoned-prefix checks use logical element order.
Both reference VLENs pass192 configurations and144 repaired signals.
Indexed restart-from-zero controls detect56 errors per ELF at both VLENs;
the shared unit-stride implementation also passes all four regression ELFs.
Controls and duplicate unit regressions add no independent coverage count.
Independent index EEWs, unordered/segment faults, aliases and other LMULs
remain separate gaps; board execution is pending.

### Integer Extension Release

`integer_forms.py` adds all 17 ordinary vector-vector arithmetic operations
in scalar `.vx` form, reverse subtraction and three high-half multiply forms.
All 22 legal shapes use five scalar boundaries (zero, seven, minus one,
signed minimum and signed maximum), seven VL points and four predicates,
including all-off. Scalar loads sign-extend to XLEN, then operations consume
the SEW-sized bits. Division includes zero and signed-overflow cases.
Each ELF checks 2940 configurations, result bits, inactive/tail preservation,
memory guards and cleared vstart. Restart is zero; this is not a repair or
passing replacement for the existing nonzero-vstart failures. Ordinary
integer immediate forms have their own independent release below.

`integer_forms.py --multiply-add` checks vmacc/vnmsac/vmadd/vnmsub,
both vv and vx, at all 22 shapes (1120 configurations per ELF). The
old destination is an explicit oracle operand. Scalar multiply-add uses
scalar-first assembly operands; destructive-multiplicand forms differ
from accumulate forms. Unsigned 64-bit intermediates avoid C signed
overflow while preserving the low-SEW modular result.

`integer_forms.py --immediate` covers add, reverse subtract, AND/OR/XOR,
and three shifts at all 22 shapes. Signed arithmetic/logic immediates use
-16 and 15; unsigned shift fields use 0 and 31, then only the low lg2(SEW)
bits control the shift. Each ELF checks 1344 configurations.

`--unmasked` separately emits vm=1 encodings for all three integer-form
families (66 ELFs, 118888 configurations). It still loads all-on, alternating,
sparse and all-off v0 patterns; all active elements must execute regardless
of those bits. Masked all-on tests alone do not establish this property.
These releases retain tu/mu, vstart=0 and explicit tail/guard checks.

`integer_forms.py --carry-borrow` checks vadc.vvm/vxm/vim and vsbc.vvm/vxm
with four v0 carry/borrow patterns (22 ELFs, 18480 configurations). v0 is
an arithmetic input, never an execution predicate; all body elements write
back even when their carry bit is zero. Reserved vm=1 data-result forms
are rejected by the builder. Subtract-with-immediate is not emitted.
`masks.py --carry-forms` adds 22 packed-result ELFs/22176 configurations
for vmadc/vmsbc, vector/scalar and legal immediate forms, with and without
carry/borrow input. The scalar oracle uses 128-bit sum/borrow arithmetic,
including UINT64_MAX+carry boundaries and signed immediate extension.
Both families check VL=0 preservation, legal mask-tail alternatives,
post-instruction vstart and output guards.

`permutation.py` adds merge/move, gather vv/vx/vi/ei16, slide up/down vx/vi,
and integer slide1 up/down. Its scalar argument stays full XLEN for offsets
and indices; only inserted scalar data is truncated to SEW. Eight scalar
boundaries include VLMAX-1/VLMAX/VLMAX+1, UINT64_MAX and the high XLEN bit.
The oracle guards before index addition, preserving slideup prefixes and
zeroing out-of-range slidedown/gather sources. Merge uses v0 as a selector;
move ignores it; gather/slide use execution predication. Three input seeds,
seven VLs and four mask patterns check inactive/tail values and guards.
All 22 shapes execute; only gather-ei16 at e8,m8 is excluded because index
EMUL16 is reserved. Other shapes retain this opcode with EEW16 index loads.
The release totals 309792 configurations, with tu/mu and vstart=0; aliases,
floating slide1 and nonzero permutation restart remain additional coverage.

`--integer-extension` builds 20 additional opcodes at all 22 legal shapes:
high-half multiply (unsigned, signed, mixed), four saturating add/subtract
forms, four averaging add/subtract forms, two rounding shifts and seven
additional integer reductions. The scalar oracle uses 128-bit intermediates,
checks all four vxrm modes and vxsat from active elements, and restores the
caller's vxrm/vxsat. All-on, alternating and sparse masks exercise masked-off
saturation suppression. Each shape checks 5,040 configurations.

Build a second release with `--integer-extension --agnostic` for ta/ma.
Inactive elements may retain their sentinel or become all ones; active
elements remain exact comparisons. VL=0 must leave the entire destination
unchanged. Combined releases plan 44 ELFs and 221,760 configurations.
Restart is deliberately zero in this extension to avoid blocking unrelated
opcode coverage on RVV-02. Nonzero restart remains a failed regression,
not a passed or omitted-from-history test. See `ISSUES.md`.

Reference validation and board execution are separate gates; a newly built
extension must not be labelled board-tested before its report is collected.

### Additional Family Releases

- `masks.py`: 23 operations across 22 shapes, including six comparisons,
  carry/borrow mask outputs, eight mask logic operations, popcount, first,
  iota, element ID and before/including/only-first masks. Four predicates
  include all-off. Each ELF checks 1,932 configurations. Mask destination
  tails permit retained, all-one or computed bits even with tu; active bits stay exact.
  Masked iota counts only enabled source bits, per RVV 1.0.
- `memory.py`: ten resident-memory operations across 22 shapes: masked
  unit/strided loads and stores, ordered/unordered indexed loads/stores, and
  two-field segment loads/stores. Positive, negative and zero load strides;
  zero-stride stores excluded because duplicated store ordering is not the
  oracle's contract. Index EEW equals SEW and VL is capped where necessary
  so offsets fit. m8 two-field segments are explicitly skipped as illegal.
  Full output buffers are checked against an independently constructed
  scalar memory image, not just the transferred active elements.
- `widths.py`: 13 widening/narrowing operations across 15 legal source
  shapes (SEW8/16/32, LMUL <=4), including mixed-sign widening multiply,
  vf2 sign/zero extension, narrowing shifts and vnclip/u. Four vxrm modes,
  active-element vxsat, three seeds, four masks and seven VL points:
  4,368 configurations per ELF. No aliasing/overlap variants yet.

These releases use vstart=0 deliberately; independent nonzero restart
coverage is tracked separately. All require both QEMU references before
`combine.py` releases immutable ELF hashes for board transfer.
`run_board.ps1` takes the board lock, can wait for a predecessor, and neither
resets nor programs the board. A processor stall preserves the scene; a
completed numerical failure does not prevent later cases from executing.

- `floating.py`: nine FP32/64 shapes, 13 arithmetic/FMA/conversion operations,
  five frm modes, sticky fflags and masked-off exception suppression. Fixtures
  include signed zeros, infinities, signaling/quiet NaNs, minimum/maximum
  subnormals, normal boundaries and overflowing values. Berkeley SoftFloat
  generates expected bits and flags on the host; all source hashes are saved.
  Each ELF checks 5,460 configurations. All five flags appear in the passing
  reference results (`flags_seen=31`); that is not yet a board acceptance.
- `exceptions.py`: four SEWs, 96 child-process scenarios each: protected-page
  mask suppression, FOF later-element VL reduction and first-element SIGSEGV.
  Expected fault children are checked through wait status; this does not prove
  their exact trap address or expand the old indexed-overlap failure into a pass.
- `context.py`: 128 asynchronous signal-return trials. A forked sender waits
  for a shared ready flag; the parent has no syscall in its live-vector-state
  window. The handler clobbers all 32 registers and vcsr. Raw registers,
  vl/vtype/vcsr/vstart and guards are checked after sigreturn. No migration
  claim is possible on this single-core image.
- `whole.py`: NF1/2/4/8 whole loads/stores at EEW8/16/32/64 and register moves,
  including VL=0 and nonzero restart. Loads/stores also run under VILL; moves
  require a legal VTYPE. QEMU10.2's >EVL host abort is a recorded reference
  limitation, not a passing test. Both references check 1,134 configurations
  with explicitly reported exclusions.

- `fixed.py`: 22 shapes, fractional multiply and saturating arithmetic,
  four vxrm values and initially clear/set sticky vxsat, including all-off
  masks. The initial flag is encoded separately from the rounding CSR.
- `reductions.py`: 32 shapes covering widening signed/unsigned integer,
  ordered/unordered FP, min/max FP and widening FP reductions. Destination
  tails use a single physical register even for m8 sources. Positive exact
  dyadic FP fixtures deliberately avoid dependence on reduction tree order;
  this does not validate NaN and inexact tree-rounding semantics.
- `extensions.py`: 28 destination/factor shapes at vf2/vf4/vf8, signed and
  unsigned. Legal high-end overlap is included only for source EMUL >= 1.
  Full physical register-group bytes, including fractional-LMUL tails, are
  checked against scalar byte images, not just the active destination array.
- `narrow_overlap.py`: 15 legal shapes with low-end destination/source
  overlap for vnsrl.wi/vnsra.wi. Masked and tail bytes are checked against
  the source preimage and the entire source group is inspected for corruption.
- `floating.py --extras`: adds fixed-RTZ signed/unsigned conversions and
  vfclass, testing all ten classification bits including both signs of
  subnormals. Five frm values must not change the fixed-RTZ result; vfclass
  must not raise flags even for signaling NaNs. These are distinct immutable
  ELFs, not replacements for earlier passing binaries.
- `segments.py`: 14 legal shape ELFs, NF3..8 resident unit/positive/negative
  strided loads and stores. Illegal group sizes are excluded before encoding.
  Active data and all output/guard bytes use scalar byte-image expectations;
  vstart is sampled before the result-dump instructions can clear it.
- `floating.py --fp16 --extras`: six FP16 shapes, 16 operations, five
  rounding modes, sticky flags and all ten classification bits. The QEMU
  references explicitly enable zfh/zvfh and preserve those CPU parameters
  in the reports/manifests; this is not evidence of board FP16 acceptance.
- `fp_widths.py`: four legal LMUL shapes for FP32/64 widening/narrowing and
  fixed round-to-odd conversions. SoftFloat supplies bit/flag expectations
  for normal/subnormal boundaries, overflow and signaling/quiet NaNs.
  Fixed-ROD fixtures must be identical across dynamic frm values.
- `fp_widths.py --fp16`: five legal FP16/32 shapes, with the same three
  conversion operations and independent SoftFloat bit/flag expectations.
  Both references explicitly enable zfh/zvfh; board acceptance is pending.
- `index_widths.py`: all 22 data shapes, independently varied index EEW
  8/16/32/64 wherever index EMUL is legal. Ordered/unordered loads and
  unique stores plus ordered duplicate stores use full scalar memory images.
  Index ranges are capped to prevent narrow-index wraparound. Ordered
  duplicate-store expectations follow increasing active element order.
- `masks.py --scalar-forms`: 22 shapes, six signed/unsigned comparisons
  in both vx and vi forms. Scalar/immediate -3 is sign-extended to SEW;
  inputs include equality, adjacent values, signed extrema, zero and all ones.
  Packed active bits and masked-off/tail policy use the same mask oracle.
- `masks.py --aliases`: 22 shapes, eight mask logic operations with the
  destination equal to either source register. Inactive bits are compared
  with the source preimage, not the non-alias destination sentinel. These
  are unmasked operations; the four predicate settings intentionally test
  independence from v0, not four distinct effective mask patterns.
- `segments.py --indexed`: 17 legal data/index shapes, NF2..8 ordered and
  unordered indexed loads/stores using independent EEW32 offsets. Index
  EMUL and NF*data EMUL are checked before assembly generation. Permuted
  unique field groups, four predicates and seven VL points are compared
  against full scalar byte images. Other segment index EEWs and exception
  restart remain untested; scalar indexed EEW coverage is not their substitute.
- `segments.py --misaligned`: nine SEW16/32/64 shapes, NF3..8 unit and
  positive/negative strided accesses at every byte offset 1..SEW/8-1.
  Vector input preload and destination dump also use misaligned addresses;
  full-buffer expected images use byte accesses, avoiding scalar alignment UB.
  Byte arrays are explicitly 64-byte aligned before applying offsets.
  Hardware alignment support is implementation-dependent: a captured trap
  is a failed capability check, not by itself a proven RTL bug.
- `context.py --nested`: 128 nested asynchronous signal events, checking
  256 live vector contexts across four VTYPE/CSR settings. SIGUSR1's handler
  establishes its own register image before a forked sender triggers SIGUSR2.
  Neither live-state window executes a syscall. Both handlers verify their
  stack addresses lie in a 64-KiB alternate stack. Raw registers, CSRs and
  guards are checked after inner and outer sigreturn; migration is not claimed.
- `fp_reduction_special.py` (plus `--fp16`): 15 shapes, ordered sum/min/max
  against host SoftFloat tables. Eight shared input scenarios exercise NaNs,
  signed zeros, infinities, finite cancellation/inexact sums and subnormals.
  Five frm modes, four predicates, seven VL boundaries and initially clear/set
  NX test exception suppression and sticky flags. Destination tails and
  guards cover the full scalar-result register. No-active copies preserve
  seed NaN payloads without arithmetic; VL=0 preserves the destination.
  Unordered rounding trees cannot be compared with a single serial sum oracle.
- `floating.py --scalar-forms` (plus `--fp16`): 15 shapes, eight scalar
  arithmetic/FMA forms, five rounding modes, four masks and seven VL points.
  Finite, zero and signaling-NaN scalars use host SoftFloat bit/flag tables.
  FP16 scalars are explicitly NaN-boxed before use; FP32 uses FLW boxing.
  Both VLEN references pass; hardware completion remains a separate gate.
- `fixed.py --scalar-forms`: 22 shapes and 15 scalar/immediate opcodes,
  covering signed/unsigned saturation, averaging, rounded shifts and
  fractional multiply. Scalars include seven and signed extrema; signed
  add immediates use -3 while unsigned shift immediates use 29. Four vxrm
  values, initial vxsat clear/set, four masks and seven VL boundaries are
  checked with the existing 128-bit scalar oracle. Each ELF checks 10080
  configurations. Nonzero restart is still an explicitly separate gap.
- `floating.py --scalar-extras` (plus `--fp16`): 15 shapes with reverse
  subtraction/division, min/max and all three sign-injection forms. Five
  scalar scenarios include finite, negative zero, quiet/signaling NaN and
  negative infinity. All dynamic rounding modes, sticky flags, predicates,
  VL boundaries and inactive sentinels are checked against SoftFloat fixtures.
- `floating.py --unboxed` (plus `--fp16`): 11 FP16/32 shapes deliberately
  leave the high scalar-register bits zero. The effective scalar operand
  must be a canonical quiet NaN, regardless of its low-bit payload. The same
  seven opcodes check min/max's single-NaN behavior, arithmetic invalid flags
  from active signaling vector operands and flag-free sign injection.
  FP64 is excluded because its operand occupies the whole FLEN64 register.
- `masks.py --comparison-aliases`: 22 shapes and six comparisons with the
  packed-mask destination overlapping either vector source's lowest register.
  Masked-off bits preserve that source preimage, not an unrelated sentinel.
  VL=0 requires preservation; mask tails allow only the documented legal
  choices. The source arrays remain independent scalar oracle inputs.
- `floating.py --destructive-fma`, optionally `--scalar-forms` and `--fp16`:
  30 shape/form ELFs for vfmadd/vfmsub/vfnmadd/vfnmsub. The old destination
  supplies the multiplicand, unlike the earlier accumulate forms. Vector
  fixtures compute old-destination * first-source + second-source; scalar
  fixtures use old-destination * scalar + vector, with the opcode's two
  signs applied before the fused SoftFloat operation. Nonfinite/subnormal
  inputs, five rounding modes, sticky flags and inactive sentinels are checked.

The following must remain marked untested until additional oracles actually
run. Presence in Ara's opcode enum is not proof of support or coverage:

| Family | Additional Checks Needed |
| --- | --- |
| Integer forms | Carry-chain and destination aliases; permutation aliases/restart; broader accumulator values |
| Fixed point | Saturation/rounding across nonzero restart; broader scalar/immediate operand values |
| Width changes | Arithmetic/clip overlap beyond extension and narrowing shifts |
| Mask results | Mask-load restart; broader scalar/immediate operands; destination-v0 special rules |
| Floating point | FP comparisons, scalar/vector moves; conversion aliases; FP16 widening reductions |
| Reductions | Unordered inexact tree-rounding and special-value alternatives; widening special values |
| Memory | Other segment index EEWs; indexed misalignment; nonzero restart; fault boundaries |
| Exceptions | Indexed/segment replay; absent versus protected mappings; >EVL whole reference gap |
| OS context | Live-state fork semantics; broader signal/preemption soak; multicore migration unavailable |

Fractional-LMUL physical register tails beyond VLMAX are checked by the
new byte-image extension/overlap suites, not the original element matrix.
Newly implemented families stay reference-only until
their numerical markers, exit codes and immutable hashes are verified on
the board. The goal is broad measured coverage, not every encoding or all
possible operand values; the exclusions above must remain visible.
See `COVERAGE_GAPS.md` for priorities, acceptance limits and recorded findings.

### Stall Continuation And Preloading

`recovery_prepare.py` verifies a contiguous attempted prefix, immutable ELF
hashes and two live no-retirement snapshots before preparing a continuation.
The original failed/stalled report is retained; by default only never-attempted
cases enter the continuation manifest. This does not turn the original batch green.
The explicit `--retry-observation-gaps` option also includes incomplete results
from a gap-aware, no-serial-write reattachment. It validates the gap reasons and
the final stalled case identity, and still requires two live no-retirement
snapshots. An I/O error, timeout or observation gap alone never permits recovery.
The new provenance records every retried gap; prior passes/failures are not rerun.
Selected pending releases are appended as a test-only newc rootfs overlay.
They reside under `/opt/rvv-preload`, not `/tmp`, which init mounts as tmpfs.
The DTB changes only `/chosen/linux,initrd-end` to include that overlay;
base rootfs/DTB hashes and new hashes are retained in `recovery.json`.
OpenSBI's embedded DTB must be updated identically: it overwrites the external
DTB at boot. The equal-sized replacement is required to lie wholly in a
loadable, allocated nonexecutable ELF section; executable sections stay unchanged.

`recover_board.ps1 -RestartAuthorized` takes the exclusive board lock and
verifies original payload/bitstream hashes before reprogramming the same
accepted image and booting the same kernel. This is an explicitly recorded
board reset, not an uninterrupted campaign. The observer subsequently
uses `--reuse-directory` and checks every guest ELF hash, avoiding repeated
UART package transfer. Pending batches wait for the continuation's actual
completion; another genuine stall preserves its new scene.

First additions08 continuation evidence: `rvv_recovery08_01`; Windows root
`D:\fpga_runs\ara_rvv_recovery08_20261009_01`. The overlay preloads 185
pending ELFs, with 62 in the stalled batch's continuation. An observer's
`board_reset=false` describes its own interval; `recovery.json` and the
recovery state record the reset preceding that interval.
If independent queues are repeatedly blocked behind a confirmed stalled
family, `recovery_prepare.py --queued-first` preserves the same failure and
all pending cases while putting queued releases first in one combined
continuation. Separate tasks for those releases must not also execute them.
That first recovery booted Linux but executed zero cases: the embedded DTB
retained the old initrd bound. This is TEST-04, not another RVV failure.
Corrected preparation `rvv_recovery08_04` preloads 200 pending ELFs, including
additions16; its 62-case continuation preserves the original stalled report.
Its first case confirms another high-end extension overlap stall (RVV-06),
with zero passing cases. Recovery05 preloads 221 never-attempted cases,
puts queued additions09..17 first and retains the 61 remaining additions08
cases afterward. Separate additions09..16 tasks are disabled to prevent
duplicate execution. The combined report is the authoritative board result;
old per-batch waiting states are not hardware completion evidence.
The audited recovery05 `resume/board_report_live02.json` contains 62 passes,
110628 passing configurations, one running case and 158 not yet attempted.
This includes all additions09/10/11 ELFs. It is an immutable live snapshot,
not a final report or a claim that the 221-case continuation has completed.
The later immutable live04 snapshot contains 103 passes and 191860 passing
configurations, 15 failures, one running case and 102 not yet attempted.
Nine failures are nonaligned preparation traps (CAP-01); six are measured
ordered FP reduction discrepancies (RVV-07). The queue continues after
ordinary failures. This snapshot is not the final campaign result.
The immutable live05 snapshot verifies 126 passes (322900 configurations),
20 failures, one running case and 74 not yet attempted. It is still partial.
Recovery05 then stops at `rvv_extension_e16_m8_vf2`: its preserved terminal
report has 140 passes (464020 configurations), 20 failures, one confirmed
stall and 60 never-attempted cases. All additions09..17 were attempted;
the failures comprise nine CAP-01 traps and eleven RVV-07 numerical failures.
Recovery06 preloads 314 immutable never-attempted ELFs, placing additions18..25
(254 ELFs) before the 60 remaining additions08 cases. Separate additions18..24
tasks are disabled. The same accepted bitstream/kernel are retained; original
reports and snapshots remain authoritative, not replaced by the continuation.
Recovery06 boots the same Linux kernel successfully. Its immutable live01
snapshot verifies 38 passes (139496 configurations) and 276 not yet attempted,
including all 26 additions18 ELFs. This is an ongoing run, not a final pass.
The later immutable live02 snapshot verifies 84 passes (217616 configurations),
one running case and 229 not yet attempted. Additions18..20 have all passed.
Additions26 and additions27 are separate hidden queued tasks, not included
in the 314 preloaded cases or the 84-pass count. Their predecessor gates
prevent concurrent serial/board access; a preserved stall requires review
before either queued task can run.
The immutable live03 snapshot has 122 passes (289296 configurations), no
failures and 192 not yet attempted; additions21 and additions22 now also
have complete board passes. Additions28 is queued after additions27 and
has no board results yet. These ongoing snapshots are not final reports.
The immutable live04 snapshot has 148 passes (330624 configurations), one
running case and 165 not yet attempted, without failures. Additions23 has
also completed all 22 board cases. Additions29 is a hidden task queued
after additions28; its reference passes are not board acceptance.
The immutable live05 snapshot has 174 passes (392504 configurations), no
failures and 140 not yet attempted. The unmasked scalar subset of additions24
has all 22 passes; its other subsets are still running. Additions30 is queued
after additions29 and has no board results yet. TEST-06 documents an old
integer comparison-alias oracle limitation without changing old evidence.
The immutable live06 snapshot has 207 passes (433720 configurations), no
failures and 107 not yet attempted. Additions24 has 63 of 66 completed passes,
not full acceptance yet. Additions31 is queued after additions30 and has
no hardware results; its drained trace and reference passes are not a fix
for the historical restart failures.
The immutable live07 snapshot has 244 passes (468328 configurations), one
running case and 69 not yet attempted, without failures. Additions24 has all
66 passes. Additions32 contains nine capability diagnostics, not nine more
independent coverage ELFs; phase1 active misalignment SIGBUS results will
remain unsupported/exit77 rather than becoming passes.

## Expansion Order

The preserved recovery06 terminal report has 258 passes (479080 checked
configurations), one confirmed stall and 55 never-attempted cases. All 254
independent additions18..25 passed; four further extension cases passed.
The next case, `rvv_extension_e32_m2_vf2`, stopped retirement (RVV-06).
Evidence is `rvv_recovery08_06/resume/report.json`, UART and both progress
snapshot directories. This is not a complete campaign pass.

Recovery07 preserves that report and preloads 279 never-attempted ELFs:
224 from additions26..33 first, followed by the 55 remaining old cases.
The separate Windows tasks26..32 are disabled to avoid duplicate execution.
They are now planned within recovery07, not independent active tasks.
No completed or stalled case is rerun or relabelled.
Recovery07 boots the original Linux successfully. Its observer PID2172 was
verified live; immutable live01 has four passes (56448 configurations),
no failures and 275 not yet attempted. This is not a final result.
Live02 records seven passes, two numerical failures and one running case.
The e8/m4 and e8/m8 large-offset slideup failures are RVV-08; execution
continues rather than stopping at the first ordinary mismatch. This later
snapshot does not change or replace the earlier live01 snapshot.
Live03 has 22 passes (284928 configurations), three numerical failures,
one running case and 253 not yet attempted. Additions26 completes with
19 passes and three failures; the third is e16/m8 (RVV-08). Ordinary
failures did not prevent additions27 from starting.
Live04 has 38 passes (374528 configurations), three failures and 238 not
yet attempted. Live05 has 46 passes (419328 configurations), three failures,
one running case and 229 not yet attempted. All 22 masked old-destination
multiply-add cases in additions27 pass; the unmasked subset is still running.
Live06 has 57 passes (480928 configurations), three failures and 219
not yet attempted. This is an ongoing snapshot, not completion.
Live07 has 63 passes (514528 configurations), eight failures, one running
case and 207 not yet attempted. All 44 additions27 multiply-add cases pass.
Five completed FP16 comparison shapes fail (RVV-09); its other shapes are
still pending. This later snapshot preserves every earlier failure.
Live08 has 67 passes (686560 configurations), 18 failures, one running
case and 193 not yet attempted. All 15 FP comparison shapes fail, including
FP32 and FP64 all-off invalid-flag trials (RVV-09). Additions29 is running;
none of the earlier failures is reclassified by later passes.
Live09 has 74 passes (987616 configurations), 18 failures and 187 not yet
attempted. Eleven FP move shapes in additions29 pass; its FP64 cases are
still pending. This remains an ongoing snapshot, not batch acceptance.
Live10 has 78 passes (1073632 configurations), 22 failures and 179 not
yet attempted. All 15 additions29 FP move cases pass. Four completed
unmasked FP16 comparison cases in additions30 fail; its other subsets
remain pending. RVV-09 now includes a concrete unmasked tail-NaN trial.
Live11 has 78 passes, 31 failures, one running case and 169 not yet
attempted. Live12 has 78 passes (1073632 configurations), 37 failures,
one running case and 163 not yet attempted. All 15 unmasked comparison
cases fail; four completed v8-alias cases also fail, with retained all-off
excess-NV examples. Other alias subsets remain pending. No pass is inferred
from a missing or running result.

`fixed.py --restart` and `fixed.py --scalar-forms --restart` add four
representable restart boundaries to all 22 legal integer shapes: one,
half VL, VL when representable, and the last capacity element. Each checks
prestart preservation, active results, cleared vstart, vxrm rounding and
sticky vxsat, including suppression from inactive/prestart elements.
The vector and scalar releases contribute 236544 and 887040 configurations
respectively per reference VLEN. Both reference VLENs pass; none of those
reference configurations is yet counted as a board pass.

`fp_comparisons.py --restart` adds masked and unmasked comparison restart
releases, with 30 ELFs and 2150400 configurations per reference VLEN.
Four start boundaries cover one, half VL, VL and the last capacity element;
all are representable at the FP shapes used here. Only active body elements
may contribute SoftFloat-derived flags. Packed prestart bits must remain
unchanged, and start>=VL must preserve the entire checked destination.
Tail bits with a nonempty body retain the ISA-permitted agnostic alternatives.
A bounded 28-line drained trace precedes selected target operations.
Both reference VLENs pass. Source-alias restart and invalid scalar boxing
remain separate gaps; this release does not claim those combinations.

`masks.py --restart --scalar-forms` and `--restart --comparison-aliases`
add 44 integer comparison restart ELFs (177408 configurations per VLEN).
All 22 legal integer shapes use four representable start boundaries, seven
VLs, four predicates and three input seeds. The source-alias oracle now
permits the different-EEW overlap's mask-agnostic inactive one bits, while
prestart and start>=VL results must stay unchanged. This corrects TEST-06
for new releases without changing the original comparison-alias evidence.
Both references pass; board acceptance is pending. Mask logic, carry mask,
vid and restart semantics of other mask operations are not implied by
these comparison-only passes.

Additions36 adds 22 permutation restart and 22 mask-logic alias restart
ELFs (1239168 and 118272 configurations respectively per VLEN). All legal
integer shapes test four representable starts. Permutation retains full-XLEN
gather indices/slide offsets, selector-versus-predicate distinctions, guarded
out-of-range sources and prestart/no-body preservation. Mask logic writes
either source register, always uses an unmasked encoding and checks packed
prestart bits and cleared vstart; ignored v0 patterns must not change results.
Both references pass. Permutation destination aliases and fractional physical
tails remain gaps. The original large-offset RVV-08 board failures are not
fixed by these new reference passes.

Additions37 adds 22 memory restart ELFs. Unit, positive/negative/zero stride
loads, nonzero-stride stores, ordered/unordered indexed transfers and legal
NF2 segments use resident aligned buffers. Four representable starts check
prestart/no-body preservation, cleared vstart, the complete output buffer
and the second segment field. Segment store setup loads both source fields
before writing vstart. The ninth C argument is read from the caller stack
without conflating restart with stride or the second-field pointer.
Both references pass (89568 configurations at VLEN512, 87264 at VLEN1024).
Counts differ because indexed VLs exceeding the index-EEW-safe range are
explicitly skipped; reserved m8/NF2 and zero-stride duplicate stores also
remain exclusions. This is not fault replay, misalignment, index/source
overlap or independent index-EEW restart coverage.

Additions38 adds 14 aligned unit/positive/negative-stride NF3..8 segment
restart ELFs and 17 ordered/unordered EEW32 indexed NF2..8 restart ELFs.
Four representable start boundaries check the complete 8192-byte output
buffer, all fields, preserved prestart elements and cleared vstart. The
wrapper preserves its incoming start before using a6 as an address pointer
and writes vstart only after all field/index/predicate setup loads.
Both reference VLENs pass (137088 and 114240 configurations respectively).
Only legal NF*register-count groups and index EMULs are generated. Actual
page-fault replay, other index EEWs, aliases and misalignment remain separate.

Additions39 adds 22 independent-index-EEW restart ELFs (131040 configurations
per reference VLEN). Legal index EEW8/16/32/64 and EMUL combinations cover
ordered/unordered loads, unique-address stores and ordered duplicate stores.
Four representable start boundaries check skipped prefixes, complete 4096-byte
output buffers, no-body cases and cleared vstart. Ordered duplicate targets
are calculated from the last active post-start element, not skipped prefix
elements. EEW8 VLs are bounded to their byte-offset domain. Both references
pass; page-fault replay, index/destination overlap and misalignment are not
implied by these resident, disjoint-buffer results.

Additions40 adds indexed NF2..8 restart with independent index EEW8,16,64
(18,18,15 ELFs respectively). Both VLEN references pass 340032 configurations.
The shared segment generator selects legal index EMULs for each data shape.
EEW8 capacities are limited to a representable power-of-two address domain,
so the index permutation stays bijective and unordered stores have unique
targets. Small-domain VL points are clamped explicitly; repeated boundaries
are not distinct exhaustive lengths. EEW16/64 keep full legal data capacity.
Four starts check complete buffers and every field. This supplements the
existing EEW32 release, not page faults, source/index aliases or misalignment.

Extend independent, short oracles before increasing soak repetitions:

1. Integer high multiply, remaining reductions, packed mask results and
   saturating/rounding operations. Check vxsat/vxrm explicitly, including
   whether masked-off and pre-vstart elements can affect sticky flags.
2. Widen/narrow and memory families, using legal register-group alignments
   and explicitly enumerated overlap rules. Cover positive/negative/zero
   stride, ordered/unordered indices, segments and whole-register traffic.
3. Floating-point flags, rounding, FMA and conversions against an
   independent reference, including nonfinite and subnormal input bits.
   Do not use the board's scalar FP results as the only expected values.
4. Exception/restart and OS state, isolated per process: guard-page mask
   suppression, fault-only-first VL updates, pending live vector state
   across signals and preemption. Run these after numerical suites because
   a processor stall can prevent subsequent command execution.

For each extension record implemented opcodes, legal shape exclusions,
executed configuration counts, reference results and board results separately.
Unsupported shapes are skips with reasons, never passes. Completing a shell
command without its numerical pass marker is not success.

`audit.py RELEASE_DIRECTORY ...` validates downloaded `board_report.json`
against the local transfer manifest, rejects duplicate/unknown case names,
and counts only unique numerical pass lines with exit code zero. It separates
completed numerical failures from incomplete/stalled cases. Pending cases
never contribute to executed configuration counts.

The existing twenty width/fault tests and thirty context tests complement
this matrix. Their failures stay failures; this package does not repair or
hide the measured overlap/fault issue. Existing QBS/AKV tests are separate
custom-operation tests, not substitutes for standard RVV coverage.

## Reference And Board Gates

Build with `build.py --out NEW_DIRECTORY --cross TOOLCHAIN_PREFIX`.
Run `reference.py` with the QEMU, BIOS, kernel and original initramfs paths.
Defaults are VLEN=512 and 1024, supported by the installed QEMU. Both must
pass using the same ELF hashes before `transfer_manifest.json` is released.
The archive is compatible with the existing board runner's `gzip -dc` then
`tar -xf` extraction. The runner must check ELF hashes and pass markers,
record exit codes and retain UART bytes. QEMU success is not a board pass.

For a preserved ALU stall, `build.py --only e8_m4 --trace-op0` makes a
separate diagnostic release. It prints each add trial's VL/mask/vstart
before execution, retaining the same instruction wrapper and numerical
checks. It does not replace or retroactively change the original release.
The last trial plus a no-retirement snapshot can distinguish a boundary
restart stall from an unrelated setup or later operation failure.

Board execution must follow the current campaign, own the exclusive serial
lock, and confirm a responsive shell. Do not reset or program the board to
deploy this suite, or interrupt another test. Restarting an unresponsive
kernel requires preserving its scene and the user's recovery authorization.

## Pending Execution Preparation

Ordered indexed segment replay passed the independent
`rvv_index_segment_reference56` job at both VLENs. The generator supports all338 legal
NF2..8/SEW/LMUL/index-EEW combinations with disjoint v16 index and v24 data
groups. Index offsets must not wrap: SEW64/index-EEW8 NF5/6/7/8 use VL7/6/5/4;
fault boundaries outside VL are omitted explicitly. The first protected
segment is kept fixed while other indices are permuted, so split-field faults
are actually exercised. Even ordered segment instructions do not order fields
within a segment, and the handler accepts any protected field at that vstart.
The complete338-case job passes32384 configurations and24272 repaired
signals per VLEN. Exact case identities, numerical counts, zero exits and
ELF hashes were validated before combining additions56. This is reference
coverage, not a board pass.
Eleven indexed-segment restart-from-zero controls, including the narrowed
VL4/VL5 cases, produce the expected numerical errors at both reference VLENs;
they are excluded from releases. All402 previous replay ELFs remain
byte-identical after the shared-oracle extension. Infrastructure tests now
also check the338-shape legality domain, nonwrapping offsets, fixed first
protected segment and disjoint prefix/suffix permutations.

Additions55 adds the matching108 negative-stride fault-replay shapes. The
low-address page is protected/unmapped; logical elements advance while
physical segment bases descend. Field offsets remain positive within each
segment. Prefix poisoning therefore checks logical restart, not ascending
address order. Both reference VLENs pass18624 configurations/13968 repaired
signals; nine zero-vstart-restart controls fail as expected and are excluded
from releases. All294 prior unit/indexed/segment/positive-stride ELFs remain
byte-identical. Zero strides, memory/register overlap and indexed segment
fault replay remain open. Additions54/55 are staged separately, not part of
the active974-case recovery11 image, and are not hardware passes.

Additions54 covers all108 legal NF1..8/SEW/LMUL shapes with positive
nonoverlapping strides `(NF+1)` and `(NF+3)` elements. It reuses the precise
signal-frame replay oracle, three fault boundaries, two page protections,
four masks, load/store directions, and within-segment page splits. Both
VLEN512/1024 references pass18624 configurations and13968 repaired signals
per VLEN. Nine restart-from-zero controls fail numerically as intended at
both VLENs and are not queued. Recompiling all186 prior unit/indexed/segment
ELFs gives byte-identical binaries bound to their earlier reference reports.
The extra focused NF8/mf8 reference is a duplicate diagnostic, not another
coverage ELF. Negative strides are supplemented by additions55; zero
strides, memory/register aliases, indexed segments and physical fractional
tails remain explicit gaps. These108
ELFs are not in the active recovery11 preload; do not reset it to add them.

The additions45..53 pending releases are also assembled into one319-ELF
execution bundle, preserving exact case order, hashes and source reference
reports. This is not319 new coverage ELFs or a hardware pass. It excludes
negative controls and duplicates of the active recovery10 plan. Recheck
newly attempted names before building any later recovery overlay.

The archived recovery10 observer sends each UART byte with a20ms sleep.
For270 passed-case samples, mean reported case time is6.03949s and the
deterministic execution-command send sleep lower bound is2.86215s (47.39%).
Hash-check command time is outside that reported interval. These are host
pacing bounds, not measured FPGA execution times. The319-case compressed
bundle is190009 bytes; its legacy base64 payload send sleeps alone would
take at least85.769 minutes. Do not select that transfer path blindly.
Prefer verified rootfs preload on an already-required authorized recovery;
do not reset a responsive board just to deploy these tests. Guest-side
batch execution retaining per-ELF hashes, exits and UART markers is implemented
in `guest_batch.py`, but is not a currently deployed observer change.

`guest_batch.py MANIFEST NEW_OUTPUT` creates `batch.sh` and `protocol.json`
with a unique run ID. Place the script beside the verified case ELFs before
invoking it in the guest. The incremental `Parser` preserves per-case output
and accepts completion only after every expected case has ended. Ordinary
numerical failures and nonzero exits continue; hash or preparation failures
abort without recording an attempted hardware case. Numerical passes retain
the existing unique-marker, configuration-count and zero-exit audit gates.
Native shell tests are infrastructure checks, not FPGA coverage results.

Deployment still requires exclusive board ownership, guest preload, and a
board adapter retaining the existing no-retirement snapshots and terminal
scene preservation. The generated pending319 script is not running on the
board. Do not interrupt recovery10 or bypass its stall diagnosis to deploy it.

`recovery_prepare.py --batch-runner` optionally adds this script to the test
rootfs overlay during an already-authorized stall recovery. It binds the
script hash and run ID to the final execution manifest in
`resume/batch_protocol.json`. The default legacy preparation is unchanged;
this option does not launch an observer or authorize a restart. It now copies
the complete observer module set and a `resume/width_suite.py` entry point
compatible with the archived recovery wrapper's `--reuse-directory` option.
Module hashes are recorded in recovery provenance. The default legacy path
does not install or change its observer. Exclusive wrapper ownership and
board validation remain required when selecting the optional batch path.

`guest_watch.py` supplies the transport-independent observation state machine.
It preserves an active case as incomplete on observation or telemetry errors,
and marks a stall only after two matching live snapshots show advancing cycles
with unchanged retired/trap/PC counters and no watchdog halt or live flags.
Completed ordinary failures do not terminate the guest batch. Native tests
exercise live stalls, progressing cores, preparation timeouts, telemetry
errors, kernel panic, protocol errors and split UTF-8 reads. This is not yet a
deployed serial adapter; recovery11 still uses the archived legacy observer.

`batch_serial.py` now implements the serial adapter for this state machine.
It verifies the local manifest/protocol/script identity, sends one short
guest-script hash check and launch command, and observes all per-case
results without sending per-case hash/execution commands. It never sends
Ctrl+C or a reset. UART bytes remain preserved; JSON snapshots are atomic
and rate-limited during output to avoid rewriting a growing report for
every read. The recovery wrapper must retain exclusive board ownership
and finish preloading before invoking it. This is not deployed on recovery11.
The first Linux/QEMU diagnostic preserved a preparation timeout because
the rootfs `/tmp` overlay was hidden by its tmpfs mount; no ELF was attempted.
The revised diagnostic uses the actual `/opt/rvv-preload` to `/tmp` copy
workflow and passes at both VLEN512/1024: the deliberate skip-body failure
exits1, the following positive ELF passes, and the batch completes without
an interrupt. The revised observer passes this diagnostic again in
`rvv_batch_adapter_reference03`; earlier evidence remains immutable.
Windows Python preflight in `rvv_batch_windows_preflight01` verifies the
copied modules, bootstrap arguments, manifest and script without opening
the serial port or accessing the board. Board validation remains required. Native adapter
tests include ordinary-failure continuation, preparation aborts, script
identity rejection, missing protocol and two-snapshot stall preservation.
The adapter drains buffered UART after a synchronous snapshot before
classifying a stall. A case that completed during diagnosis, or its next
case, cannot inherit stale no-retirement evidence. Native tests verify both
races. This does not alter the currently running legacy observer. The tool
suite passes107 tests, including package/module identity and default-path
compatibility checks.

Zero-stride fault replay passes the independent
`rvv_zero_stride_reference57` job (108 legal NF1..8 shapes), with3104
configurations and2328 repaired signals per reference VLEN. The focused nine
shapes pass both reference VLENs; nine deliberate skip-body controls fail
numerically at both VLENs. Unordered duplicate stores use uniform per-field
values rather than an assumed last-writer order. These checks do not verify
device-memory access counts or completed-prefix replay. Existing402
reference-validated ELFs rebuilt byte-identically after this extension
(`rvv_fault_identity_regression57/identity_verification.json`). No new board
pass is implied by these reference results. Additions57 contains only the
108 positive cases; controls and duplicate focused diagnostics are excluded.

The immutable `pending_releases_after_recovery11_v3.json` queues662 positive
ELFs from additions54..57. All four packages are staged on Windows with
manifest/archive/per-ELF SHA256 verification. They do not duplicate active
recovery11 cases and no pending board task has started. Append them only at
normal completion or an already-authorized preserved-stall recovery.

The immutable recovery11 `board_report_live03.json` contains29 passes and
151 failures, with no active case in that between-case snapshot. Unit m1
fault replay reports48 signals rather than the reference36 and32 numerical
errors; this is consistent with the retained protected-page/all-off finding,
not a newly proven internal RTL cause. The observer was confirmed live
immediately before collection and ordinary failures continue. This is an
ongoing snapshot, not a terminal batch or system acceptance.

Read-only background monitoring is active in `rvv_recovery11_monitor01`.
It checks the fixed observer PID and creation time every120 seconds,
atomically saves a consistent report and preserves a separate terminal
report only after both a terminal report state and a missing observer.
Observation errors do not trigger resets or classify the board as stopped.
It does not open COM6, invoke Vivado or launch queued cases. The board
observer's existing two-snapshot stall gate remains responsible for prompt
hardware-stall diagnosis. Pending662 cases remain separate from recovery11.

`inventory.py` aggregates explicitly selected campaign releases and board
reports by `(ELF name, SHA256)`, not report/snapshot count. Repeated snapshots
and shared release entries cannot inflate coverage. Running snapshots can
be superseded by the same ELF's completed result; a later pass does not erase
a failure, stall or incomplete attempt. Such conflicting outcomes remain
explicitly mixed. Passes require one line-start numerical marker, a positive
configuration count and exit0. Changed-image reports are rejected, and
different ELF hashes never borrow another version's result.

The immutable `rvv_inventory01/inventory.json` selects additions03..57,
verifies all released ELF hashes and binds its source report hashes. It
contains2767 distinct ELFs (2752 coverage and15 focused diagnostics):1075
passed,332 failed,8 stalled,1 running and1351 not attempted at that snapshot.
There are no outside-release board results in this selected evidence set.
The662 queued cases are included in the1351, not extra attempted coverage.
These are global execution outcomes, not an exhaustive ISA pass or a terminal
current-batch report. Older immutable failures and stalls remain retained.

The later immutable `rvv_inventory96/inventory.json`, through recovery83's
terminal scene, retains the same2767 distinct ELF identities:1889 passed,
740 failed,81 stalled and10 not attempted, with no outside-release results.
There are47 mixed historical outcomes in a separate count category, not47
additional selected tests. Recovery84 preserves all10 pending hashes.
Numerical failures are completed executions, not acceptance passes. Stalled
ELFs lack their final numerical marker and leave subsequent inner trials
uncovered. Exhausting the pending ELF queue therefore cannot by itself prove
complete configuration coverage or hardware acceptance. Scene-specific
evidence and unresolved causes are recorded in `ISSUES.md`; RTL is unchanged
during this measurement campaign.

`rvv_inventory105/inventory.json` includes the final recovery89 scene and
has no running or never-attempted selected ELF. Its2767 outcome categories
are1889 passed,744 failed,87 stalled and47 mixed historical outcomes.
Mixed is a separate category in `counts`, not included in passed/failed/stalled;
it must be included when reconciling the total. All selected ELFs have been
attempted, but stalled ELFs still lack complete internal configuration results.
The final terminal scene was archived without another board recovery.
This is an execution-queue milestone, not completion of full coverage or
numerical acceptance. The remaining internal-trial gaps require explicit
follow-up rather than relabelling stalled cases as finished.

### FP move operation partitions

`fp_moves.py --operations 1 --restart --only e32_m8` builds a separate
`rvv_fp_move_restart_e32_m8_ops1` ELF for broadcast, retaining every seed,
scalar value, boxing variant, VL, mask, restart point and sticky-flag setting.
Indices0..7 retain the original `OPS` order and shared assembly/oracle;
omitting `--operations` preserves the original full-loop behavior. Distinct
names and hashes prevent a partition result from borrowing the original
ELF's outcome. No selected configurations are removed from the parent plan;
partitions are follow-up evidence for its blocked operations, not replacement
acceptance for the parent ELF. Invalid/duplicate selections are rejected.

`rvv_fp_move_partition_smoke01` verifies op1/e32/m8 at both reference
VLEN512/1024:21504 configurations each, errors0 and exit0. This validates
the partition's reference semantics, not FPGA execution. Other partitions
still require their own exact-ELF reference and board results before counting.

The default-loop rebuild in `rvv_fp_move_default_identity01` reproduces the
released additions31 e32/m8 ELF exactly:SHA256
`8ef698364963c9949196096ebb1dda21efc9d7c10cb42cd4d12dfe69afb12555`,
with unchanged172032 configurations. This checks default behavior for one
representative shape, not identity of every rebuilt shape. Full partition
preparation is recorded separately in `rvv_fp_move_partitions02`; the earlier
partitions01 preparation stopped on an incorrect QEMU executable path before
any reference execution or board access and is not validated evidence.

`rvv_fp_move_partitions02/release` completes both exact-ELF references for
all120 operation partitions,2236416 configurations per VLEN, errors0/exit0.
`parent_mapping.json` binds each original additions31 name/hash to eight
children and checks that their operation indices and configuration totals
cover the parent plan without omissions. This is not original-ELF execution
or a hardware pass. Recovery90 publishes this new queue after the archived
recovery89 stall. `recovery_prepare` permits an exhausted old queue only
when a nonempty new queued-first selection is validated; the confirmed-stall,
reference, archive/hash, executable and observer protocol gates remain.

### Pending-case scheduling

`execution_order.py` provides a stable, optional order for immutable pending
cases: unmasked FP comparison restart first, then other non-m8 combinations,
then remaining m8 combinations, then segment-alignment diagnostics. FP move
partitions containing masked slide-up/down (operation2/3) follow those groups,
because operation-specific completion stalls have been captured. Partition
LMUL is read from the manifest, not inferred from the `_opsN` name suffix.
Extension partitions containing high-end overlap (operation2/3) are likewise
deferred, so ordinary-source m8 extensions can run before known-risk overlaps.
This is a risk heuristic based on campaign stalls, not a pass prediction or
a proven common RTL cause. Every pending ELF remains selected exactly once;
its source, ELF hash, reference results and numerical oracle stay unchanged.
`recovery_prepare.prepare(..., execution_order=names)` records the exact order
and rejects omissions, additions and duplicates before building an overlay.
Explicit order overrides earlier prefix priorities and deferrals.

### Extension operation partitions

`extensions.py --operations 0 --only rvv_extension_e16_m8_vf2` retains the
original assembly and oracle for one operation. Operation0/1 are zero/sign
extension with separate sources;2/3 are their legal high-end overlap forms.
All seeds, lengths, masks and physical-register-tail checks remain selected,
84 configurations per operation. Omitting `--operations` retains the full
original loop. Invalid selections and fractional-source overlap are rejected
before any output is created. `extension_oracle.c` is shared with the narrowing
suite; its default mask selects every existing operation in both suites.

`rvv_extension_partitions01/default_identity` reproduces all14 blocked
additions08 parent ELF hashes exactly. The56 child ELFs are independent
follow-ups, not replacements for those parent stalls. Reference generation
and any eventual board outcomes must be verified independently; preparation
alone does not establish hardware coverage or success.

The prepared `rvv_extension_partitions01/release` has now been independently
checked:56 ELF hashes,112 reference results at VLEN512/1024,84 configurations
per child,4704 configurations per VLEN, errors0/exit0. The14-parent mapping
retains all four operations per original shape. Reference passes alone do
not count as FPGA passes. Board audits of recovery94 terminal and recovery95
snapshot01 now verify all28 ordinary-source operation0/1 children:2352
configurations, errors0/exit0. Signed high-end overlap e16/m2/vf2 stalls;
the remaining overlap children are not accepted. Exact evidence and probe
limitations are recorded under RVV-06 in `ISSUES.md`.

The combined176 FP-move/extension partition inventory at
`rvv_partition_inventory04/inventory.json` is a frozen recovery95 snapshot01:
72 passed,46 numerical failures,5 confirmed stalls,52 never attempted and1
running. The118 completed numerical outcomes include failures, not118 passes.
These follow-up identities must not be added to the2767 parent inventory as
independent instruction coverage or used to overwrite original parent results.
Other stalled families and internal trials remain unresolved; completing this
partition queue alone is not completion of the whole coverage goal.

The current board batch is never reordered in place. The supervisor applies
the policy only when preparing the next authorized original-image recovery
after a confirmed two-snapshot no-retirement stall. Ordinary numerical
failures continue without a reboot. Host-side audits can proceed while the
single board runs its batch; simultaneous board suites would contend for
the core and serial port and invalidate isolated measurements.

For the observed Windows owned-Vivado-tree cleanup failure, the observer
may retry the whole read-only snapshot pair once, in new evidence directories.
This requires a snapshot-command failure report naming that cleanup error
and an existing readable snapshot artifact. Generic transport/telemetry
failures still stop; a repeated cleanup failure also stops. Failed captures
are preserved and never used as either member of the accepted pair. Recovery
still requires the unchanged two-successful-snapshot no-retirement gate.
The change applies to newly prepared observers, not a running batch.
