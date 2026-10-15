# NF8 Original192 Sv39 Reference

Independent full-scope successor to `../sv39/`. No production RTL changes,
no edits to accepted four-case sources/ELFs/helpers, no NF7 rerun or progress
queries, and no192-case DUT launch. This directory has software compiler/Spike
entry points only; future DUT execution needs separate parent approval.

## Exact Original Scope

All zero-based trial IDs0..191, grouped as group g = trials4g..4g+3, for48
independently selectable four-case ELFs. Original enumeration is unmapped0/1,
store0/1, boundary1/3/5, mask mode0..3, gap1/3, split0/1, outermost first.
No representative substitution or reordering. Masks ff/aa/24/00; stride36/44;
VL8 e32/mf2 tu/mu; fields v24..v31. Expected faults144, no-fault alloff48.

`reference.py` regenerates all192 geometries independently and compares each
with the pinned original-source selection ledger. It verifies identity57
C/generator hashes, original ELF identity and exact regenerated archived S.
The unchanged original S is linked into every new ELF. Original Linux ELF:
`c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282`;
original assembly: `63c68bc8c2c935884520082cd423c51e9f14fb7caac7a42816026b9597acb8db`.

These are source-derived S-mode/Sv39 programs, **not Linux ELF execution**.
They do not prove Linux SIGSEGV delivery, siginfo ACCERR/MAPERR, signal-frame
layout, context save/restore, or scheduler behavior. Original169/later128
errors remain unlocalized. Even full192 DUT PASS would be source-derived
architectural coverage, not automatic Linux failure closure.

## Preserved Oracle

Use the accepted NF2-derived runtime and NF8 four-case oracle. ACCERR uses a
valid execute-only data leaf with MXR0; MAPERR an invalid leaf. Real page fault
cause/PC/tval/VL/vtype/vstart/PTE and CSR capture, addressed SFENCE and unchanged
PC/vstart retry are required. Complete active prefix is checked before repair,
then poisoned XOR5b to expose replay from zero. All cap16 field words, old vd,
inactive/tails, physical fractional tails, neighbor registers, guards, full
8192-byte backing and gaps, PTEs, masks/input/output buffers and CSR restoration
are checked. Firsterror keeps original trial/phase/kind/index/got/want.

Fault-segment partial fields remain implementation dependent. Load active
fault/later elements are not overconstrained at the saved-prefix checkpoint.
Accessible store fields may independently be original or correctly stored,
never a third value. Protected fields and non-target bytes stay exact. Tval
may identify any protected field of the expected element. The observed Spike
field order is not imposed as a DUT field-order or segment-atomicity rule.

Only immutable input and register seed initialization plus root/middle page
table initialization are shared within a group. Every case still checks these
full buffers. Data pages, output, trap/result snapshots, mask/stride, PTE leaf,
records and counters are reset per case. Original target/setup/readback and
whole-memory checks are unchanged. Each phase has a checkpoint, each case a
comparison counter; four-case count, restoration, magic and exit are mandatory.

## Preparation State And Entry Points

`reference01/group00` passed real Spike for trials0..3 with12370 comparisons and
1001948 retiring commits. Its current-source host check covers all192 formulas:
909504 rows. `host01` is an earlier formula-only artifact, not the final pinned
reference acceptance; use `reference01` and the campaign pins below.

`reference.py --out <fresh-owned-dir> --groups <0..47>` builds both SoC and
Spike ELFs and validates real Spike plus independent negative/byte-state
oracles. Each Spike has a90s hard process timeout. It never invokes VCS.

`reference_campaign.py prepare --out <fresh-owned-dir>` prepares the complete
48-group map and pins. `worker` reuses accepted group0 and runs remaining even
and odd groups in two bounded software-reference workers, failing/cancelling
the other partition on any failure. One admission checks live simv+Spike+two
reservations <=24 and MemAvailable>=32GiB; no capacity polling or retries.
The reference service has a7200s outer limit and local stdout/stderr logs.

Only a terminal `HOST_SPIKE_ALL192_PASS_NOT_DUT` with exact192 membership can
claim full reference completion. Running partitions and host-only checks do
not count as full Spike or DUT PASS. Proposed DUT budgets are in `VCS_PLAN.md`.
