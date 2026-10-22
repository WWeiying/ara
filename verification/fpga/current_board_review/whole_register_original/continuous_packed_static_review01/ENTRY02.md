# Corrected02 Reference Entry

NO_BLOCKER_REFERENCE_ONLY; machine-readable binding is ENTRY02.json. Hilbert
may execute the already-authorized single bounded complete reference. This
does not authorize DUT or claim packed-reference PASS before execution.

The only header semantic delta is the reviewed `in + (offset - 32)` fix.
Actual input pointers now stay within the array; no alias cast was added.
Empty/guard paths return before pointer formation; partial shifts are bounded
to1..7 bytes. Corrected Host02 binds the actual header6e11dc9e..., not the
blocked e5e82b... header. Its local1134 geometry/word differential proof checks
all byte positions at initial error counts0/11/12, exact original diagnostics,
cross-word guard errors plus prior status error, and864 changed-current-input
cases. The full converted-main Host confirms original order and fresh arrays.
No Host was rerun by this reviewer.

Independently checked every listed code instruction against actual ELF PT_LOAD
bytes: SoC1675 and Spike1725 entries. All20 complete helper encodings per
backend (620 instructions) match the old original helper bytes. No extra RVV
or memcpy libcall; input/output are64-byte aligned. Actual lowering contains
128 input sd iterations,136 output sd iterations and scalar ld comparison.
The current-input address calculation uses integer subtraction before addition.
Correction legitimately changes ELF identity; no old ELF hash is substituted.

Actual audit wiring calls SetupLedger.store on post-main input/output writes,
requires previous call completion before reinitialization, uses the NEXT
original tuple's seed, and consumes/reset setup coverage at every helper entry.
Final counts require1134*128 input stores and1134*136 output stores. Ordered
eight-byte output reads expand into all1088 original expected bytes per call.
Fresh-ledger six Host tests were explicitly reused from identical parent code
with original exit0 receipt and pins; they were not represented as new runs.
Completion-cache semantic code is unchanged. The original helper/path/argument/
status/CSR/console/HTIF/parking checks remain.

The program's packed expected word reads CURRENT post-helper input. The
independent reference output checker additionally compares against the source
initialization formula; original helpers do not modify input. This is not a
replacement of the C oracle with a cached expected-output table. Local changed-
input tests explicitly distinguish the two.

All107 bound input hashes matched in this read-only review. Decoder path uses
OLD.parents[3]/coverage; parser consumes the actual corrected Spike spec and
the same reference_bound01 digest passed by reference.py. Reference status
FULL1134_PACKED_REFERENCE_PASS_NOT_DUT matches the executor gate. Exclusive
reference01 prevents retry. Actual child waits are saved before postchecks,
and all pins/review identity are checked afterward. Bounds remain40Msteps,
120s/4GiB and600s parser, one attempt. No raw was read and no compile/reference
was repeated by this reviewer. Full DUT remains unadmitted pending actual cost;
over3h means HOLD, not scope reduction or timeout growth.
