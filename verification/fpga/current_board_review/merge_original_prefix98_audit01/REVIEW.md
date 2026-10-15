# Integer merge op4 e16/m8 prefix98: independent source/reference review

**ACCEPTED_SOURCE_REFERENCE_PREFIX98_ONLY_NOT_DUT. No blocking source or
reference discrepancy found.** This review can be bound by a subsequent DUT
plan, but is not launch authorization or DUT acceptance. The historical
recovery159 stall has `last_trial=null`; **it is not closed by this98-call
software reference**. Full2688-child, later seeds/scalar slots and Linux
execution remain outside this review.

## Bound Identities And Scope

Producer directory: `../merge_original_prefix98_prepare01`.
READY SHA256:
`8381b90ee089c90be273faca67b8096f802f628f655fd5756a186ef57b3ed175`.
All **97 distinct dependency/artifact pins** matched before and after the
audit (29 baseline entries plus73 owned entries, with5 duplicates). Raw
`commits.log` was hashed during the single independent full parse, not in
additional full-file hash passes. Producer files were not modified.

| Identity | SHA256 |
| --- | --- |
| Original Linux ELF, partition/recovery159 | `275c9d872111a37c28e7466b7fbd7f263a545918315b8a98284d456950d22118` |
| Authentic shared original C | `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca` |
| Original operations.S | `40bce22639d00865881e06337270ed76fd37e01c7891296471934accbf7afbcf` |
| SoC ELF | `4e495abc1ec6b553554c5ddee992db88234c969adcba2f92b90ed6c78ea245ab` |
| Spike ELF | `48a6cf76563eb0bbaf771858532237bd0a2c49d7edd3abf8021f1df1d8607e96` |

Archive paths are under
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`:
`rvv_permute_partitions01/release/binaries/rvv_permute_restart_e16_m8_ops4`,
the same-named S/header directory, and `rvv_recovery08_159/terminal_scene`.
The shared C retained at
`rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c` matches
the original manifest C hash; its storage name does not change the selected
integer merge provenance. The archived ELF is stripped: the audit recovered
the unique contiguous13-code sequence and verified actual ELF bytes. It
does not claim a byte-identical rebuild of the entire original Linux ELF.

Only established runtime adaptation, the stop **after** call98's complete
original oracle, the exact98 count check and explicit PREFIX final marker
change the source. Both stored diffs were reproduced exactly. Compile
records retain `SEW=16`, `RESTART_PERMUTATIONS=1`, `PERMUTE_OP_MASK=16`,
`-march=rv64gcv`, `-mabi=lp64d`; the Spike runtime alone adds its existing
`SPIKE_REFERENCE` selection. No compile was performed by this reviewer.

All97 predecessors are retained. The first96 calls cover VL0/1/2/3/256/511,
each with all4 masks and4 original restart trials, including duplicates.
Call97 is VL512/mask0/start1; call98 is VL512/mask0/start256, tuple
`[0,4,0,6,0,1]`. This is not all mask/start combinations at VL512. The
original filtered op0..3 loop history and seed0 RNG are retained; no warmup
or skipped selected predecessor was introduced.

## Original13 And Merge Semantics

Each word below matches the actual original Linux, SoC and Spike ELF:

| Step | Encoding | Instruction |
| --- | --- | --- |
| 0 | `00b772d7` | `vsetvli t0,a4,e16,m8,tu,mu` |
| 1 | `02055407` | `vle16.v v8,(a0)` |
| 2 | `0205d807` | `vle16.v v16,(a1)` |
| 3 | `02065c07` | `vle16.v v24,(a2)` |
| 4 | `02b78007` | `vlm.v v0,(a5)` |
| 5 | `00b6f2d7` | `vsetvli t0,a3,e16,m8,tu,mu` |
| 6 | `8e42` | `mv t3,a6` |
| 7 | `00889073` | `csrw vstart,a7` |
| 8 | `5c880c57` | `vmerge.vvm v24,v8,v16,v0` |
| 9 | `00802573` | `csrr a0,vstart` |
| 10 | `00b772d7` | `vsetvli t0,a4,e16,m8,tu,mu` |
| 11 | `02065c27` | `vse16.v v24,(a2)` |
| 12 | `8082` | `ret` |

Target PCs are original `0x10684`, SoC `0x80000798`, Spike `0x800007e4`.
For every body element `[vstart,VL)`, selector1 takes `indices[i]` fromv16;
selector0 takes `input[i]` fromv8. Selector0 is **not masked-off preservation**.
There is no gather indexing or OOR-zero rule: values512/513 remain integer
merge data. Only prefix/tail preserve initialized halfword0x005b.

The independent model starts from original64-bit seed0xE736815B449AEC21,
applies each13/7/17 xorshift with64-bit wrap, then truncates input to16 bits.
Index choices and both arrays, all128 predicate bytes, all514 output/guard
halfwords, scalar0, actual a1 ordinary-index pointer and original unused
`mv t3,a6` are retained. It independently matches every Host fixture value
and all98 tuples, then checks actual raw state rather than trusting fixture
or producer PASS labels.

## Independent Full Raw Findings

One pass of the existing130671353-byte raw log produced SHA256
`200cae142a2c252b21fea3f15b0a15727943e0367de06a98dbe138a2769f0452`.
No new Spike, original Host suite, VCS, build or live-query command was run.

| Check | Actual independent result |
| --- | --- |
| Selected helper windows / every13-PC count | 98 contiguous windows / each98 |
| Full input, old-vd, predicate and result vectors | All98 checked |
| Full vector stores | All98 checked,512 exact address/value pairs each |
| Scalar result elements / guards | 50176 /196; total50372 LHU reads |
| Returned-vstart zero / actual vset returns | 98 /294 |
| Selector-zero / selector-one body elements | 2722 /2669 |
| Capacity helper | Exactly1 original window |
| Unused helper interiors / other RVV | 0 across the other20 helpers /0 |
| Source bootstrap vector CSR PCs | `0x8000002e`, `0x8000008a`, `0x8000034a`, each1 |
| Firmware retirement through HTIF success | 2020160 |
| Boot retirement | 5, exact boot PC/code sequence0x1000..0x1010 |
| Post-HTIF park | 4835 original `0x8000007e:a001` records, no side effects |
| Entire raw retirement count | 2025000 =5+2020160+4835 |

Every firmware retirement PC/encoding matches actual Spike ELF bytes, all
helper windows are strict, and neither trap handler has a retired PC. The
first target is firmware retirement63052; the last is2009425. Full source,
vector result, store and scalar oracle checks include prestart and tail.
The reconstructed console exactly matches the stored runtime log: one
original PREFIX PASS, case begin/pass and replay PASS; no failure/DETAIL.

Actual command/profile: pinned restartgold Spike
`c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2`,
`--isa=rv64gcv_zvl1024b -m2 --log-commits`, original Spike ELF above.
Integer SEW16 does not require FP16 arithmetic extensions. The stored process
exited0 in3.426291472s, with actual HTIF store1 at original exit PC/address.
The debug command has `rs 5000000`, not a claim of5M executed instructions;
actual exit occurred earlier. Original120s/5M/768MiB bounds were unchanged.
The4835 post-success records are explicitly checked, not dropped from scope.

Stored Host evidence was read, not rerun: the positive reports98 calls,
errors0/rc0; all9 negatives report98 calls, one injected error/rc1. Log hashes
match the supplied gate. Legacy negative name `inactive` means selector-zero
body, not inactive merge behavior. Existing5 raw corruption and3 window
negative results are preserved producer evidence, not newly executed tests.

## Budget And Subsequent Admission

Measured software work is2020160 firmware retirements, not measured VCS
merge performance. The old273 retired/s planning proxy gives7399.85s,
or **8879.82s with20% margin**. Thus **9000s/case,10200s outer service, jobs1**
is a reasonable bounded proposal under3h, but has only120s remaining margin
at that conservative rate. No automatic retry, extension or reduced oracle
is justified by this estimate.

For context, the independently accepted M6 VI0 terminal previously measured
4882457 retirements/8372.603877s =583.15/s; applying that different-workload
proxy gives3464s, or4157s with20% margin. The producer's same-shape670.2/s
proxy implies3014s/3617s with margin, but its originating performance report
was not independently re-audited here. Neither proxy guarantees merge time;
reference and SoC scalar runtimes and actual vector stalls can differ.

A future runner must bind this exact READY/SoC ELF and review, keep all98
calls and50372 data/guard checks, distinguish merge selector-zero from
masked-off preservation, reject partial `RVV_PERMUTE_DETAIL` immediately,
and close the full unused-helper/extra-RVV retirement scope. Image/resource/
service/abort/terminal gates and actual DUT admission require separate review.
No historical stopped tuple is inferred, and no original stall is closed.

Independent machine-readable decision: `audit.json`, SHA256
`63ec9e40827c334f849a1d8d64a6dad3ab52d07ed8b1236c8f7f9a9477b9072f`.
Independent script SHA256:
`1872c6c114cf27c9389ddf90bb7f77b7a544c9b92fde01a3e35ac374aa905f3f`.
