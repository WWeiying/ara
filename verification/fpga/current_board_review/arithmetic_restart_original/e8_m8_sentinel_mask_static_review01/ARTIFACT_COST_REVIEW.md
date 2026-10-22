# Actual Artifact And Cost Review

Decision: **NO_BLOCKER_SOFTWARE_ARTIFACT_COST_ONLY** for the exact successor
below. Source diff, bounded short C checks, actual dual compilation and linked
success-cost gate are accepted. Reference and DUT remain **not authorized**.
No original fullstream execution or new architectural correctness is claimed.

## Identity And Receipts

Producer directory: `../full_e8_m8_sentinel_mask_software01/`.

| Artifact | SHA256 |
| --- | --- |
| SOFTWARE_READY.json | d2d24d346f016b474b351ae26d96cd26a10afb72e95d04d2805b5c49cc736327 |
| LINKED_COST.json | f1f7cd9b30666f772a229e7df5f02d9b75506b7fc6a8beabc84ca791a52a1200 |
| COST_REPORT.md | db230dc29f43a5525aca99eaad420e20632d12205ba4440ec0dabaab855ad0b1 |
| SoC ELF | 57a9513e3c4c9cd292f0bcea2596a898edd563dbb4380b63be4d33942f66596c |
| Spike ELF | b1cd154e319211187f8e6e34f7e8f40398ebdc65f035e033ed7b8f8141d15c0c |

Existing numeric receipts: preparation PID3636168 rc0/6.982754s; short C
PID3636179 rc0/0.009948s; compiler PID3636180 rc0/2.070925s and PID3636196
rc0/1.069314s; static CFG PID3636212 rc0/132.530227s. All report timeoutfalse,
retries0. This reviewer did not repeat any execution.

Short C evidence covers nine actual ordinal gold outputs, 9234 individual byte
mutations, 384 mask-byte mutations and six wrong modes, using undefined-behavior
sanitizer with trap-on-error. Guard-page placement checks the 2B actual tail
without permitting an overread. This is bounded C comparator/mask evidence,
not a full4095 Host stream or proof of actual vector operation semantics.

## Independent Artifact Checks

The union of 65 producer input/output pins matched on independent read. Both
new ELF hashes match receipts. Actual command comparison confirms unchanged
optimization/ISA flags except the new source/output paths, inherited-header
iquote path and map output. Quoted packed.h resolves next to the new case.c;
dictionary and operations/helper sources remain inherited immutable inputs.

All original 328 static helper instructions (capacity3 plus 25x13) match the
old backend bytecodes. No new RVV instructions appear outside these helpers.
Every decoded instruction byte in each listing was independently matched to
its ELF PT_LOAD bytes. No old CFG walk or producer CFG execution was repeated.

Source diff remains exactly the accepted sentinel branches and mask expansion;
case.c/fallback is byte-identical. The 4095 saved helper-argument records were
independently compared to original sequence.json: a/b, out+1, original VL,
CAP1024, mask and vstart match for every ordinal. The reviewed producer CFG
checks actual per-call input values, initialization/store coverage and mask
epochs against inherited seed/table data, rather than merely cardinalities.

Actual e8 geometry remains CAP1024/vtype3/physical8 with 1024-byte a/b objects,
1026 checked output bytes, 128 complete output LD plus final LHU. SoC tail LHU
is at0x80000624, Spike at0x80000630; both address out+1024. Main frame remains
304B; stack gaps are654824 and646368B, within the inherited1MiB layout and
above64KiB. Mask stores cover all128 bytes in each of1575 epochs, not an e16
upper-half-zero assumption. No extra e16-size BSS input shadow is needed.

Clarification of SOURCE_DIFF_REVIEW wording: initialization is **128 eight-byte
copies plus one two-byte copy**, not128 total bytes. All1026 fresh bytes remain.

## Actual Constant And Cost Accounting

Independent tally of the saved PC visits and actual linked instructions finds
16 sentinel-construction sites. Each executes LUI/ADDI/SLLI/ADD; each step's
visit count agrees, totaling52335 constructions and209340 instructions. It is
not one materialization per call. Equality chains between successive actual
words are valid here: the first checked word is sentinel, and every subsequent
word must equal the previous checked word before execution can proceed.

Both backend comparators cost1686072 instructions versus old451x4095=1846845,
so the actual conditional comparator reduction is160773 instructions. All
new ID branches, joins and repeated constant constructions are included.

Comparator scalar loads total707445:
- Actual output:528255, unchanged.
- Nonzero-ID gold fullwords:105480 LD.
- Gold tail:4095 LHU.
- Original IDs:69615 LHU.
- Literal-pool and stack loads:0 in this linked comparator, not assumed from C.

Thus the comparator-only load reduction happens to equal418680 for this
lowering. That is **not a whole-program memory-read or runtime reduction**.
Whole-main counts separately include60249 loads and584467 stores. Its constant
pool accesses, setup, spills and joins are not omitted from instruction cost.

| Positive-path term | SoC | Spike |
| --- | ---: | ---: |
| Main, including all setup/branch/join/spill | 820503 | 812312 |
| Comparator | 1686072 | 1686072 |
| Capacity plus original helper bodies | 53238 | 53238 |
| Direct and nested numeric printing upper | 4881 | 7281 |
| BSS loop | 1637 | 5737 |
| Remaining startup/return success allowance | 20000 | 20000 |
| **Total upper** | **2586331** | **2584640** |

Independent sums match LINKED_COST and SOFTWARE_READY. The startup allowance
is conservative for the inspected finite straight-line startup/main-wrapper/
exit remainder; the only startup loop, BSS clear, is separately charged. It
does not bound indefinite park iteration or error/trap execution. The cutoff
is successful backend exit, not any amount of post-exit parking.

## Scope And Remaining Gate

This full positive-CFG estimate explicitly assumes each original helper returns
vstart0 and vector data equals the original immutable oracle. It is not a Spike
reference run, instruction receipt from firmware, failure-path bound or wall
time estimate. The3M software cost gate passes; no <3h DUT guarantee follows.
Old timeout/closed2601-prefix evidence remains unchanged and does not imply
deadlock, complete4095 acceptance or original Linux closure.

No blocking artifact finding remains for this stage. Any later reference entry
must bind these new PCs/ELFs, full4095 source and oracle, all128+tail2 reads,
actual mask/setup and exit contracts. No reference, DUT, RTL, extra compile,
Host rerun, raw/active CSV read or budget increase was performed by this review.
