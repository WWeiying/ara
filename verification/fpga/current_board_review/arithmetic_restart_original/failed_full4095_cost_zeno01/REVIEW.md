# Historical Stalled Full4095 Cost Review

Static only,2026-10-14. No compiler, Host, Spike, DUT, RTL edit, full CSV read or
FP700 progress query. Existing metadata/source and selected original hashes were
read. Only this independent report is new. Relative paths are from
verification/fpga/current_board_review/arithmetic_restart_original.

## Selection

Choose **original rvv_matrix_e8_m4, all4095 calls**, for the next software-only
feasibility preparation. Do not substitute a historically passing shape, new
singleton, accepted56 prefix, MACC482 or fixed777. Those are not full4095 closure.
Current evidence supports a legitimate optimization route, NOT an unconditional
claim that the full program already fits3h. Reference measurement is still needed.

| Historical stalled shape | CAP | Full result elements | Result+guard bytes/call | Exact packed reads/call | Accepted M4 prefix |
| --- | ---: | ---: | ---: | ---: | ---: |
| e8/m4 |512|2096640|514|64 aligned8B + final2B =65|56 |
| e8/m8 |1024|4193280|1026|128 aligned8B + final2B =129|38 |
| e16/m8 |512|2096640|1028|128 aligned8B + final4B =129|56 |

All three are25 integer operations,3 seeds,4095 original calls,8190 guards,
4095 returned-vstart checks and53235 original helper instructions. None is full
accepted. E8/m4 additionally has an authentic captured stall boundary at original
zero-basedtrial55, seed0/op0/VL512/mask0/vstart256. E8/m8trial37 and e16/m8trial55
are source-derived prefix boundaries, not captured original final tuples.
E8/m4 uses half the per-call source/destination vector bytes and scalar oracle
bytes of the other two. This is stronger evidence than selecting by small SEW alone.

## Original Materials And Identity

Archive A=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04.
Source/oracle: recovery22/reconstructed_oracle.c, SHA
7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91.
Original C text is not recovered; recovery22/report.json proves binary-equivalent
full Linux rebuild and disassembly for all22. No original-C-byte claim is made.
Manifest A/manifest.json and prepared02/original_identity.json bind original
compiler, headers, generated assembly, capacities and historical evidence.

Fresh original and rebuilt Linux ELF hashes agree for each:

- e8/m4:5b77ae16b4316cb33e507d488103b9a31a12db6e371e60cec95092858f382ad8.
- e8/m8:ee9874270f50735cb04da599bb477d3d9da2bbeba0e77cbec9e1eb1ea0f8310f.
- e16/m8:68fc999069ab1f830f6dc4c572f1ebe851c8511b412aa355cd5e0fabe9a4ef7d.

Original ELFs: A/overlay/opt/ara-tests/rvv_matrix_{e8_m4,e8_m8,e16_m8}.
Rebuilt ELFs: recovery22/rvv_matrix_{e8_m4,e8_m8,e16_m8}.
Assembly A/rvv_matrix_e8_m4.S SHA
78ad748eccefa3453777ac07271699edf470a091882fe7f4078b1247712f4350;
e8/m8 assemblye0dd3eb419e65813853869548fe54e278457005db90e032ed4a64ecb8aa5be08;
e16/m8 assemblya55d6f07a2f69258ffe07378baf08cf72fab2283312b76a8a8b5a5637b35d191.
A/e8/operations.h and A/e16/operations.h both hash
7686eb17f96d500c82711d09bbaa74c965352b4257b0b7db3510d3fbbd9bf48c.
No new full4095 bare-metal ELF/reference is present for these three.

Accepted prefix authority: candidate04_plan01/complete.json and TERMINAL_AUDIT01.md.
Historical captured e8/m4 evidence: archive ../rvv_trace02/manifest.json,
uart.bin, report.json and rvv_matrix_e8_m4.S; original trace assembly equals the
base matrix assembly. Full original report/snapshot/reference pins are listed in
prepared02/original_identity.json and the existing preparation pins. Readiness
of source/binary/oracle is established, not Linux execution or a current root cause.

## Reliable Measurements, Not A Full Runtime Prediction

| Accepted M4 prefix | Actual VCS seconds | Retired instructions | Same-layout naive4095 seconds |
| --- | ---: | ---: | ---: |
| e8/m4,56 calls |1776.947779|1174462|129939 (36.09h) |
| e8/m8,38 calls |2372.816167|1469207|255702 (71.03h) |
| e16/m8,56 calls |1679.199823|1098023|122791 (34.11h) |

Actual prefix reference firmware:1180150,1474919,1103733 respectively, from
prepared02/reference/status.json. Rates660.94/619.18/653.90 retired/s come from
the measured DUT metadata, not new runs. Scaling op0 prefixes to all25 operations
is intentionally only an illustration of the original scalar-cost problem:
division/reduction/compress have different vector and oracle costs. It is not a
bound. O2 alone has no demonstrated order-of-magnitude reduction here; accepted
e64/m1 O2 reduced reference firmware23.35%, far below the roughly12x+ runtime
reduction indicated by even these naive figures. Do not propose O2-only DUT first.

Closer mature packed-scalar evidence, read without reparsing CSV:
macc_disjoint482/full482_optimized_prepare01/vcs_m8_plan03/prepared01/complete.json
and its replay/tests/macc_disjoint_e8_m4_prefix482_scalar64/strict_full482.json.
It has the same e8/m4 CAP512,482 original calls,31330 packed reads, full246784
results/964guards,821220 retirements (6 parks), actual2032.843667s. Effective
firmware rate is about403.97/s. It is a calibration, not arithmetic4095 coverage;
it lacks the full25-operation division/reduction history.
The other mature FP682 packed run is about497.86/s; using only that faster rate
would understate uncertainty. Neither rate guarantees M9 timing.

At the slower403.97/s,10800s with20% margin supports approximately3.64M firmware
instructions. Set a software feasibility target <=3.0M for extra uncertainty.
3.0M projects about8912s with20% margin;4.4M would project about13070s and FAIL
the3h admission assumption. VDIV/VREM hardware latency may reduce throughput
further, so firmware count is necessary but not sufficient. No measured full4095
cycle profile exists; a short vadd prefix cannot certify all25 operations.

## Legal Packed Scalar Route For E8/M4

Keep original seed -> op -> VL -> mode -> start loops. Keep every duplicate-zero
position, all3 seeds/all25 operations, capacity once, input/RNG special values,
arrays a[1024]/b[1024]/out[1026] and physical mask[128]. Exact lengths are
0,1,2,3,256,511,512. Keep all original13-instruction helpers byte-identical:
three full-cap source/old-vd loads, MaskM load, target vtype/VL/vstart, target,
returned-vstart and full-cap output store. No warmup/reset/interposed vector/FP
operation; no fflags oracle invented for this original integer suite.

1. Leave original a/b xorshift initialization once per seed intact: it is small
   relative to4095 calls, and retaining it avoids inventing a different RNG history.
   A later input-ROM optimization is unnecessary for the first feasibility attempt.
2. Replace mask construction with scalar copies from three exact128B masks, each
   derived from this CAP512 predicate rule (including upper64 zero bytes). Still
   perform the copy every call; do not skip because mode repeats. Use aligned
   uint64_t may_alias copies, autovectorization disabled, no added vector helper.
3. Fill exactly514 destination bytes with64 aligned8B sentinel stores and one2B
   tail store. Do NOT cast out+1 to uint64_t: it is deliberately unaligned. Do
   NOT round stores to520B or touch the previously unused original array tail.
4. Read exactly those514 bytes each call:64 aligned uint64_t loads from out base,
   then one unsigned16-bit load at base+512. Leading/trailing0x5b guards are inside
   those comparisons. This covers every2096640 original result and8190 guards,
   not a checksum, sample, early pass or only active elements.
5. A flat full-value oracle ROM is too large:4095*65*8=2129400B, beyond the
   original1MiB software linker budget. Instead deduplicate immutable expected
   **64-bit values**, not calls. Every call keeps65 uint16 indices pointing to
   the exact expected-word dictionary; actual output is compared exactly to each
   looked-up value. Tail dictionary value compares only the exact2B width.
6. Static representation bound:23 primitive output forms*3 seeds*65 words*3
   predicates <=13455 interior values; window boundaries <=7749; compress full
   packed forms plus boundaries <=648; reduction first-result values <=63 plus
   sentinel variants. Conservatively <=22000 dictionary words (176000B) and
   532350B full call-word indices, plus optional65520B descriptors,384B masks,
   code/BSS/64KiB stack. This is a plausible sub1MiB layout, NOT an actual linked
   memory proof or measured distinct-word count. E8/m8 and e16/m8 need1056510B
   of indices alone, so this same representation cannot fit their1MiB link budget.
   They need another legitimate compression layer and roughly double check work.
7. Oracle generation must implement original unsigned/signed division corner
   cases, slide inactive prefixes, VLMAX gather bounds, masked modular reduction
   and compact ordering independently. Reduction writes element0 for nonzeroVL
   regardless of predicate bit0; compress selects packed prefix length rather
   than ordinary active-window positions. Do not reuse one arithmetic mask for
   these operations. On comparison failure, retain the original slow per-element
   oracle/reporting path so original error counts/details and first cause remain;
   success counters still equal4095/2096640. No state/history skips are permitted.

## Falsifiable Cost Target And Next Authorized Work

There are266175 complete packed-word comparison groups. A scalar unrolled lookup
needs output load,index load,dictionary load,address calculation and comparison;
an illustrative7..12 dynamic instructions/group gives1.86..3.19M check instructions.
Packed initialization/mask copies, unchanged helpers, original call loops/RNG and
reporting add further work. Approximately3..4.4M total is a design hypothesis,
not compiler or execution evidence. The upper end does NOT meet the conservative
3h calibration. Small bounded unrolling is useful; giant generated code/unrolling
that threatens text/stack bounds is not assumed.

The most useful next task is source-faithful **full e8/m4 software preparation**,
not another static inventory or a new small control. In a fresh successor:
prove exact original full-ELF identity; retain all helpers and4095 call positions;
prove the complete dictionary against the original C oracle/inputs; check every
position and negative active/prestart/inactive/tail/guard/vstart cases; compile
one scalar-only O2 derivative; verify all actual helper/code windows/no extra
vector instructions/1MiB layout+64KiB stack; then one bounded full Spike reference
and one strict whole-source audit with actual numeric receipts. That future
preparation needs authorization; nothing was executed by this review.

Require measured own full firmware <=3.0M as the preferred budget gate, or explicitly
report any larger measured count and residual division-cycle uncertainty before
considering DUT. No >3h automatic extension, no arbitrary short prefix, no reset
partition relabeled full. If the software cannot achieve this while preserving
all values/history, the honest result is "full4095 not yet budget-feasible", not
replacement by a passed shape. Full source-port PASS would still not equal
unmodified Linux/tty-drain/timing-history closure.
