# Next Original Batch03: NF2 Only

2026-10-12. Bounded read-only source/manifest/terminal-report review. No raw
CSV reread, build, Host/Spike/DUT execution, RTL edit, or extension-group audit.

## Final Selection After Parent Review

**This section supersedes the earlier four-case proposal below.** Exactly the
following four are selected; each exists in the40, has an independently failed
single/exit1, and is absent from J4. No further case search is needed.
Common source directory prefix is
`H/singles/rvv_small_fault_segment_nf2_e16_m1_`, with H defined below.

| Final suffix | Original case.json measured context | Intended oracle |
| --- | --- | --- |
| u0_s0_b1_m2_f1 | sig11/code2, address273693114368 vs expected273693114370; PC68394 matches; vstart1 vs2; VL8/vtype8; faults1/expected1; handler_errors1/errors1 | Sparse load: inactive element1 field1 at P must not fault; first active denied element2, restart2 |
| u0_s1_b1_m2_f1 | sig11/code2, address273693114368 vs expected273693114370; PC68456 matches; vstart1 vs2; VL8/vtype8; faults1/expected1; handler_errors1/errors1 | Same geometry, store; no completed active prefix before fault |
| u1_s0_b5_m3_f1 | sig11/code1, address273693114368 vs printed expected273693114378; PC68394 matches; vstart5 vs printed8; VL8/vtype8; faults1/expected0; handler_errors1/errors2 | All-off load against unmapped page: NO fault; printed8/P+10 are no-active sentinel values, not desired trap context |
| u0_s1_b5_m3_f1 | sig11/code2, address273693114368 vs printed expected273693114378; PC68456 matches; vstart5 vs printed8; VL8/vtype8; faults1/expected0; handler_errors1/errors2 | All-off store against protected page: NO fault and no target writes |

Precise independent-single contexts are separately retained in
`evidence/single_board_report.json`: load b1 has address273763262464 versus
273763262466, PC68372; store b1 has273270931456 versus273270931458, PC68400;
all-off u1 load has273292046336 versus273292046346, PC68356; all-off u0 store
has272779571200 versus272779571210, PC68416. Each actual PC equals its expected
PC, every status is failed/exit1, and the vstart/fault/error signatures match
the corresponding sequence context above. Do not conflate relocated PCs/bases.

| Final suffix | case.json SHA256 | scenario.c SHA256 | scenario.elf SHA256 |
| --- | --- | --- | --- |
| u0_s0_b1_m2_f1 | `e0c5c5ed1c9de7c0819c360b45b479b1a649b9d7aff961dc4a88f044599fd856` | `732d5e8b81a4338a8c1a7e3615b750873c74aba26027659f3341b531b60ea5c8` | `241d8027160cf211e37966ae8cf77d5d426fc7ddb7b9761616aebd8cc864d256` |
| u0_s1_b1_m2_f1 | `d7cec382432005fc3a129d48610ccf98386f15a8368e4e79881f37d9b5c08799` | `d19a965c5036dd79cffc8be0ea41317e99b72a72cbfa2538d6c8c710fa67976a` | `0769cc6a3b088c79b6491e62baf42af0e0c0282900daba7c8825c97a28479c7a` |
| u1_s0_b5_m3_f1 | `b7fbc59eefab8a565e93eacbcdda55811b53983375a01f5d1ef1190579ddcddc` | `4b40a12ba7cdbb34410d13bf117b7daf57daf89e4787330a9d0968f649d0592d` | `a83227383ae11672dd56a9652f01c58410e817e909cfc1caf23931e0ade8615a` |
| u0_s1_b5_m3_f1 | `2233d79a84c62dcfcc7a6665de106bc560c20dfaa29905b651c5c335ee9b33e1` | `42de5782abf2f9d1ab68b8b9eda86115aa1edce9c4755da2a1850992742430c6` | `5c16bc2a24821ec57e4301788c126734bd42d4b24e1a5fefa97ff1a635063ec2` |

All four actual C/S/ELF hashes match their manifest entries. Common scenario.S
remains `de5487a9ec451569e10485d8e2a78e458b7c519e417aee31bffded645569a7ac`.
Each C selector at line210 explicitly picks the table's exact tuple before
initialization. Full96-parent zero-based indices are5/29/71/47 respectively.

Final oracle implications: b1 pair uses baseP-6 and mask0x24. Element0/1 are
inactive, so neither load nor store has an active completed prefix to poison;
retain the original poison loop, which is correctly empty at restart2. Both
fields of active elements2/5 must ultimately pass the full data oracle. The
faulting element2 may be partially completed; retain original field allowances.
All-off pair uses baseP-22/mask00; no handler/retry is permitted and terminal
vstart is0. Preserve both64-element fields, guards and every halfword of8KiB
memory. u1 remap/refill occurs only as post-target cleanup for this nofault case.
No independent numerical failure is inferred from errors1/2.

J4's b3/m2/f1 load/store and b5/m2/f1 positive controls do not duplicate any
of these. The final batch intentionally does **not** retest completed-active-
prefix poison, already exercised by J4; it tests the first-active fault and
all-off field-split paths. A source-faithful real-Sv39 adapter is appropriate,
but original Linux signal ABI and unmodified Linux ELF acceptance remain out
of scope. Static selection is complete; no preparation or execution started.

## Deduplication

Archive root H:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_segment_fault_handoff01`.
`evidence/single_manifest.json` contains exactly40 NF2/e16m1 singles.
`evidence/single_symptoms.json` contains40 matching confirmed failures.
Actual selected single outputs/exit1 were read from `single_board_report.json`.

The40 are `(u,s)` in `{0,1}x{0,1}`, each with these ten `(b,m,f)` tuples:
`(1,2,0),(1,2,1),(1,3,0),(1,3,1),(3,2,0),(3,2,1),(3,3,0),(3,3,1),(5,3,0),(5,3,1)`.
Here u=protection/unmapped, s=load/store, b=boundary element, m=mask mode,
f=split. Mask mode2 is0x24; mode3 is0. Initial vstart is0, not the name's s.

Existing accepted M2 Sv39 four-case program, per
`masked_translation/segment_review/sv39/DUT_REPORT.md` and CURRENT_SCOPE:

| Existing tuple | Relation to40 |
| --- | --- |
| u0/s0/b3/m2/f1 | One of40, accepted source-derived load |
| u0/s1/b3/m2/f1 | One of40, accepted source-derived store |
| u0/s0/b5/m2/f1 | Historical positive control, not in40 |
| u0/s1/b5/m2/f1 | Historical positive control, not in40 |

Thus **2/40 failed-single geometries covered,38 not covered by that program**:
14 sparse-mask failures and24 all-off failures remain. Do not subtract all4.
Existing extended8 is NF1; accepted NF8 full192 and NF7 indexed do not add
NF2 identities. This is an inventory deduction from existing reports, not
a fresh independent revalidation of their raw traces or current-image rerun.

## Earlier Proposal (Superseded)

Every source directory is `H/singles/rvv_small_fault_segment_nf2_e16_m1_<suffix>/`
and contains `case.json`, `scenario.c`, `scenario.S`, `scenario.elf`.
All four were independently reproduced as standalone board failures, not just
identified as the last printed point of a stalled long program.

Let P be the denied second-page start, M=P-4096. All have NF2, e16m1,
VL8/vtype8, v24/v25, cap64 at VLEN1024. Address is `base+4*i+2*field`.

| Priority / suffix | Base and intended behavior | Actual archived single failure | Added distinction |
| --- | --- | --- | --- |
| 1: u0_s0_b1_m2_f1 | P-6; mask24; first active denied element2, fields P+2/P+4; one load fault, vstart2 | vstart1 at P, expected2; sig11/code2; handler_errors1/errors1, exit1 | Empty completed-active prefix; an inactive segment's second field crosses P before the first active access. Existing b3 had completed element2. |
| 2: u1_s1_b3_m2_f0 | P-12; mask24; completed element2 at P-4/P-2; denied element5 at P+8/P+10; one store fault, vstart5 | vstart3 at P, expected5; sig11/code1; handler_errors1/errors1, exit1 | Unmapped/remapped page, non-split field geometry, and both-field completed-prefix poison must survive retry. |
| 3: u0_s1_b5_m3_f1 | P-22; mask00; no fault and no target memory changes | one store fault at P/vstart5, expected zero faults; handler_errors1/errors2, exit1 | All16 NF2 field micro-ops must skip, including a field-split boundary; no store W/B generated by the target. |
| 4: u1_s0_b1_m3_f0 | P-4; mask00; no fault and destination remains old | one load fault at P/vstart1, expected zero faults; handler_errors1/errors2, exit1 | All-off NF2 completion against a missing mapping, with no handler/retry permitted. |

For all-off records, printed expected_start8 is an oracle sentinel for
"no active denied element", **not** a desired fault at vstart8. Terminal
vstart must be0. For sparse faults, retain the original allowance for any
denied field of the correct element rather than overconstrain to field0.
The original full96-program zero-based call indices are5/84/47/54 respectively;
they identify source linkage, not a requirement to execute unknown prefixes.

### Context Classification And J4 Complementarity

For candidate1, `case.json.measured_trial` retains the original sequence
context: address273693114368 versus expected273693114370, vstart1 versus2,
handler_errors1. The separately measured standalone single has a different
mapping base (actual273763262464 versus expected273763262466), but the same
P versus P+2 and vstart1 versus2 discrepancy. Do not replace either original
record with the other, or treat ASLR's absolute-address difference as a bug.

The inactive segment1 has field0=P-2 and field1=P. Both must be suppressed
under mask0x24; it is not an active partially completed segment. Correct fault
ownership is active segment2, with denied fields P+2/P+4. Retain the original
field-address allowance and exact element/PC/VL/vtype/fault-count checks.

**No independent numerical bug is established by these four records.**
Candidates1/2 each have errors1 accounted for by handler_errors1; candidates3/4
each have errors2 accounted for by handler_errors1 plus the unexpected fault
count. These are exact historical predicate/translation/exception-context
failures relevant to the existing mask-translation repair. The full numeric
oracle remains mandatory regression protection, not evidence of another root.

The four selections remain complementary after J4 deduplication:

- J4 already tests *active* segment5 field1 crossing, for both load and store
  (b5/m2/f1 positive controls). Do not add those again as failed-source cases.
- Candidate1 adds *inactive* field1 crossing before the first active load;
  no completed active prefix exists, unlike J4's b3 cases.
- Candidate2 adds sparse store with completed-prefix poison, unmapped/remapped
  backing and split0. This retains a different geometry instead of merely
  repeating J4's u0/b3/split1 store.
- Candidates3/4 add all-off store/load ownership and completion; J4 has no
  all-off case. Candidate3 includes a field1 page boundary, but no field is
  architecturally permitted to access memory.

## Exact Identities

The selected files were rehashed against manifest C/S/ELF identities; no mismatch.
Common scenario.S SHA:
`de5487a9ec451569e10485d8e2a78e458b7c519e417aee31bffded645569a7ac`.
It retains both v24/v25 preload/dump helpers, mask load, VL8 setup, exact
`vlseg2e16.v` / `vsseg2e16.v` targets and post-target vstart read.

| Suffix | scenario.c SHA256 | scenario.elf SHA256 |
| --- | --- | --- |
| u0_s0_b1_m2_f1 | `732d5e8b81a4338a8c1a7e3615b750873c74aba26027659f3341b531b60ea5c8` | `241d8027160cf211e37966ae8cf77d5d426fc7ddb7b9761616aebd8cc864d256` |
| u1_s1_b3_m2_f0 | `74b76c15dc0326bea2c9e0ffd32b9f9eea3077b9d78e5a0046c648e9867a3999` | `fa246ba2d27000250e59608cac0e8b721e57075d60a18f44afeb065f87edef50` |
| u0_s1_b5_m3_f1 | `42de5782abf2f9d1ab68b8b9eda86115aa1edce9c4755da2a1850992742430c6` | `5c16bc2a24821ec57e4301788c126734bd42d4b24e1a5fefa97ff1a635063ec2` |
| u1_s0_b1_m3_f0 | `975b1cbb2641c239b2c4b4f83cae4e4512dfed24389cddae509bb3ff602766dd` | `4aa2e68ba14c612cbfa2a02c39b9297fb41c67d34903b7ab0a0ddb5c2bf0cd58` |

Selected case.json hashes in that same order:
`e0c5c5ed1c9de7c0819c360b45b479b1a649b9d7aff961dc4a88f044599fd856`,
`0f2dea227a1b9b88a82cccb27b43b04bffd44ba40e8c89f8f0cf9ee5c3233e75`,
`2233d79a84c62dcfcc7a6665de106bc560c20dfaa29905b651c5c335ee9b33e1`,
`614f55dad2783c16443099480b8b8c252a12fb394780662678172e65f844647e`.

Original parent ELF:
`H/controls/rvv_trace_fault_original_segment_nf2_e16_m1/scenario.elf`,
actual SHA `3fb155679a00980cc07e34a858e7eea84c1c390e6af054f8f868ee03ba6c7054`.
Singles explicitly have `scenario_role=single_current_oracle_trial` and
`original_rebuild_byte_identical=false`. Their confirmed standalone failure
does not prove byte-identical original Linux per-trial execution. Preserve
this provenance distinction rather than call a future port the original ELF.

Evidence SHA256:
- single_manifest.json: `97082460c49c616812562991c6a1fd1fee4e516c68538b869d221a2dd2249535`
- single_symptoms.json: `a1f54b8fd008792d4e10efabd35c287d36778a0b36e9ed523d43e555ec886181`
- single_board_report.json: `48469c93985bab5737ceacb20c04705b0f16e23183643103171e9eb3471e3706`

## Necessary Setup And Full Oracle

No RNG or preceding vector history is needed to reproduce these *standalone*
records: each selected C filters at line210 before mapping, then initializes
both pages, all field inputs/output and mask. Retain the complete helper setup,
not a direct AddrGen injection. Data formulas and checks must remain:

- Memory halfword at A: `uint16_t(((A-M)/2)*37+11)` over the entire8KiB.
- Store source at field f/index i: `uint16_t(101+13*i+29*f)`, all64 each.
- Load old destination0x005b; output includes both64-element fields and two
  original guards. Preserve all tail/inactive elements, not just VL8.
- At sparse fault: check target PC, exact expected vstart/VL/vtype and both
  fields' completed prefix before repair. Permit partial completion of the
  faulting segment as the original does; never demand all its fields untouched.
- Repair page, poison ONLY completed active prefix in both fields with XOR5b,
  and retry the same PC with preserved vstart/registers. Candidate1 has no
  completed active element to poison; candidate2 poisons element2 in both fields.
- At completion: vstart0, correct fault count, all128 output values, guards,
  and every halfword of both pages. All-off performs no target writes and no
  page-fault handler; map/permission restoration is only post-target cleanup.
- u1 must retain remap/refill semantics. A future Sv39 fixture must explicitly
  replace mmap/munmap/mprotect/signal handling, preserve the inaccessible page
  distinction and original data initialization, and add its established PTE,
  neighboring-register and CSR checks without weakening the original oracle.

These address/predicate/restart faults are suitable for a real-Sv39 VCS port.
Linux signal-frame layout, SEGV_MAPERR/ACCERR delivery and sigreturn themselves
still need Linux; they cannot be claimed from that port. Existing NF2 fixture
hardcodes mask24/start5 and all four cases fault: it is **not directly reusable
unchanged** for this batch. Copy to a successor and parameterize only the
explicit mask/fault-start/unmapped/zero-fault differences, after authorization.

## Bounded Next Action

Prepare exactly these four in a new successor using the proven NF2 runtime
and observer. First independently check complete Host/Spike oracles and cost;
then bind the unchanged ELF to the current frozen image, with no RTL changes.
If measured software cost exceeds a3h/DUT-ELF ceiling, stop rather than reduce
the data oracle. No launch is authorized or performed by this review.

Comparable actual cost: the accepted old four-case NF2 ELF took1590.94s
simulation /1640.46s including observer on candidate02,4133 checks. This batch
keeps the same full buffers and only two trapping cases, but introduces
remap/refill. A provisional **3600s inner /4200s outer, jobs1** is reasonable
for planning, not a measured cost or guarantee; finalize after reference cost.

If a mismatch occurs, discriminate segment element/field/VID and mask
owner/window, AddrGen skip-versus-MMU acceptance, final load writeback or store
B/done, exception vstart, and unchanged-PC retry. The existing predicate repair
predicts these may pass; none is claimed to be a currently reproduced defect.
Their value is filling four exact historical, complementary and untested NF2
identities, not rerunning known passes or inventing an unknown-last-trial prefix.
