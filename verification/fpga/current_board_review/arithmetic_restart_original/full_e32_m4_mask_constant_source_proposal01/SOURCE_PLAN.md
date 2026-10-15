# e32/m4 Ordered Constant-Mask Stores: Static Proposal

Status: **PENDING_INDEPENDENT_STATIC_REVIEW; COST_HOLD**. This directory is a
new source-only proposal, not a replacement for any sealed artifact. No C
compiler, Host execution, Spike, DUT, live query, or RTL edit was performed.
Hilbert's prior review approved the source-model prerequisites, not this
new scalar lowering. No further execution is authorized by this document.

## Narrow Change and Fixed Scope

Replace only the selected-mask scalar read/OR/write computation with the
same ordered byte stores of statically known cumulative values, after the
existing proposed 128-byte zero phase. `mask_constant.h` is the concrete
candidate. Every clear chunk and selected store has an empty compiler memory
barrier, not a hardware fence. Selected writes additionally use a volatile
uint8 lvalue to expose each byte-store obligation. All three source modes
are present; invalid modes trap instead of selecting an easier valid mode.

This **changes scalar implementation and scalar instruction identity**.
It does not preserve original LBU/ORI instructions and must never be described
as doing so. e32/m4 has not established a sealed LBU-retirement contract.
The sealed e32/m2 and e64/m4 LBU/expected-LD contracts remain unchanged.

Fixed obligations: actual CAP128/physical4/vtype18; all5985 original calls and
their complete predecessors; original helpers (458 static instructions),
RNG and integer inputs; per-call FP a[i],b[i] writes (256 ordered SW for each
of1890 FP calls, 483840 total); 766080 results, 11970 guards, 5985 returned
vstart checks; full520B output initialized and all65 actual LD per call;
original typed mismatch fallback and error accounting. No fflags oracle is
added or claimed. Capacity must be checked at runtime before this fixed-CAP
helper is used. It cannot silently adapt to another capacity.

## Source Basis and No-Other-Writer Premise

`../recovery22/reconstructed_oracle.c:16-17` declares separate private a, b,
out and mask arrays. Lines113-116 clear all128 mask bytes for every group,
then visit each selected i in ascending order. There is no call between the
clear and selected loop or between selected updates. Trials and vector helper
calls occur only afterward (lines117-138). The mask argument is const in the
operation prototype (lines20-22). The bound original `.S` consumes it through
`vlm.v v0,(a5)`; output stores use a2, not the mask pointer a5. Source recovery
does not introduce threads, signal handlers or a DMA writer to this private
array. This is a single-program fixture transformation, not a safe general
replacement for read/modify/write on shared or MMIO memory.

The original source identities are those bound by
`../full_e32_m4_source_model01/generated01/input_pins.json`. Original ELF SHA
`4e537be1270d607f847b8c7d3d4e7be76b9b7408d184effc33a9c066cb811cf9`, recovered
C SHA `7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91`.
The C is a binary-equivalent reconstruction, not original-C-byte provenance.

## Equality at Every Store, Not Just Final Mask

For mode m, let S_m be the increasing sequence of selected source indices.
For each j in S_m, original byte offset is b=floor(j/8), and its value after
that store is

```text
V(m,j) = OR { 1 << (k mod 8) : k in S_m, k <= j, floor(k/8) = b }.
```

All bytes are initially zero and no other writer intervenes. Induction on
the selected-store ordinal therefore gives exactly V(m,j) for the source
LBU/OR/SB and the candidate constant SB. The base case is the first selected
bit in that byte; the inductive step adds the next distinct bit, preserving
all earlier bits. Stores to other bytes do not affect the recurrence. This
proves equal address, value, order and count after **each** selected store.
The LBU contributes no independent observation under these source premises.

| Mode | Selected indices | Per-byte cumulative values | Stores/group |
| --- | --- | --- | ---: |
| 0 | 0..127 | 1,3,7,15,31,63,127,255 | 128 |
| 1 | 1,3,..127 | 2,10,42,170 | 64 |
| 2 | 2,9,..121 | Explicit ordered list below | 18 |

Mode2 pairs `(byte offset, cumulative value)` are:

```text
(0,4) (1,2) (2,1) (2,129) (3,64) (4,32) (5,16) (6,8) (7,4)
(8,2) (9,1) (9,129) (10,64) (11,32) (12,16) (13,8) (14,4) (15,2)
```

The intermediate stores `(2,1)` and `(9,1)` are mandatory. Their omission,
even though the final byte still becomes129, violates the contract. Likewise
mode0 is not sixteen stores of255, and mode1 is not sixteen stores of170.
The original 735 groups of each mode retain 735*(128+64+18)=154350 selected
SB, after2205 complete clears. Proposed clear lowering is16 disjoint exact8B
memcpy stores/group (35280 total). Upper112 bytes remain zero and physical
mask backing is128B even though vlm consumes16B.

This proposal's candidate constants are written out from these formulas.
The prior complete source/math model's `mask_source_ledger.bin` contains the
full group/phase/address/value ledger, SHA256
`ea05bfe27cd1c40614d1402e42fee491bd109ed7e3d6676fdce3949a0e51ff0a`.
This phase has not executed the candidate or repeated the model.

## Necessary Counterexamples and UB Boundaries

- Missing clear: if byte0 starts0x80, mode0's first original update writes
  0x81, whereas a constant1 store writes1. The transformation requires fresh
  zero proof for **each group**, not only a zero BSS at program entry.
- Concurrent/intervening writer: if byte2 changes after the i16 store, the
  i23 source RMW could retain that change; the proposed constant129 may not.
  Compiler barriers do not make that situation safe or provide synchronization.
- Wrong capacity/mode or reordered/omitted selected store invalidates the
  induction. Full source tuples cannot be replaced by final-mask equality.

Every selected offset lies0..15 and value lies0..255. The source proposal
uses no variable shifts; no shift-width, signed-overflow or sign-extension
ambiguity is introduced. uint8 accesses may alias the mask object legally.
Clear memcpy chunks cover exactly0..127 without overlap or out-of-bounds
access and do not form a uint64 pointer into a byte array. The future buffer
must have alignment suitable for the intended SD lowering; C memcpy itself
does not require it. Width, zero-phase ordering and exact SB materialization
remain future actual-GCC/trace checks, not assertions based on macros alone.

The static function adds no new RVV, no runtime table, no loop over modes,
no target operation and no hardware fence. At most210 selected constant sites
exist across the three branches. A rough LI+SB form is420 scalar instructions
(1680B at4B each), plus16 clear stores and dispatch/prologue. This is a text
estimate, not measured encoding or an actual frame/map claim. Constant reuse,
compressed instructions or spills can alter it; no benefit beyond the
conservative single-LBU removal per selected update is assumed here.

## Optional Immutable Expected Cache

The only cache considered is the previous exact64B **expected ROM** block,
with eight scalar expected words and an exact canonical dictionary ID tag.
Reset it on every call. On a miss, load all eight expected words, then update
the tag; on a hit, reuse them. In either case perform all eight distinct actual
loads and comparisons for that output block. Handle the ninth block's valid
8B separately (element127 + rear uint32 guard), never read its56B ROM padding
from the actual output. All65 actual reads occur even on an earlier mismatch;
the original fallback then retains every typed error check.

Exact canonical ID equality is equality of64 bytes, not a hash assumption.
Invariant: before comparing word k, cache[k] equals that current block's ROM
word k. A miss establishes the invariant and a same-tag hit preserves it.
Actual output data never supplies cache contents. Full5985 reconstruction in
the existing source model confirms this representation; it is not compiled
cache code validation. Ordinary software must never return early because an
actual block looked equal to a prior actual block.

Existing exact dictionary:2252 blocks/144128B plus107730B IDs; listed ROM
254834B, full planning envelope422930B including64KiB stack. Adjacent-cache
counts:33123 full-block hits,14757 misses including5985 first blocks,5985
final-word loads. Expected loads fall389025->124041 (264984 saved); actual
loads remain389025. The all-unique-block ideal120393 expected loads is not
the implementation proposal: keeping up to64 expected-value registers would
not fit. Stack-spilled cache loads must be charged, not counted as free reuse.

## Cost: Promising Combination, Still HOLD

Replacing LBU/ORI/SB with LI/SB removes **at most154350 instructions** under
that simple lowering assumption. The candidate does not establish emitted
instructions. No constant-reuse benefit beyond this allowance is booked.
Cache tag decisions, assignments, address calculations, branches, stack
spills and caller costs remain unmeasured.

Using the prior *illustrative*, not measured,3384640 firmware anchor:

```text
3384640 - 264984 expected LD - 154350 selected LBU = 2965306
nominal margin to3M = 34694, before cache-specific overhead/corrections
```

There are41895 later full-block tag decisions, already more than that margin
if charged as one extra branch each without offsetting savings. Avoiding
dictionary address calculations on33123 hits could offset some cost, but
that requires actual lowering evidence. Applying the same gross savings to
the earlier3699825 static allowance still gives3280491. These are not actual
CFG bounds or proof that the combined proposal either passes or must fail.
The immutable cache plus constant stores is mathematically eligible, but
**does not yet admit a3M reference or a DUT run**. No bound increase, truncated
scope, alternate flags or blind candidate run is proposed.

## Review and Subsequent Gates

Hilbert reviews this precise header/proof and current input hashes first.
No Host/compile is performed by this static task. If later admitted, one
integrated candidate must preserve all existing source/oracle obligations
and demonstrate:

1. Every selected-store event matches the existing ledger, not just final
   masks; delete/reorder/change an intermediate SB and the check rejects it.
2. Clear omission, wrong upper-byte clear, wrong mode/capacity, and wrong
   address/value/width fail. Known equal old values never waive fresh writes.
3. Cache wrong-tag/stale-value/high-word/last-word faults are rejected; a
   dropped actual read is rejected even when its expected/output value repeats.
4. Actual GCC emits16 zero SD/group and154350 ordered selected SB overall,
   preserves483840 FP SW and all389025 actual reads, with no extra RVV or
   helper-byte drift; full tuple/RNG/gold/fallback remain original.
5. Actual code/frame/map and a conservative full-history CFG cost establish
   the unchanged3M gate before any reference. A source estimate is not enough.

No new tests or execution have been run for these prospective gates. This
document does not authorize modification of previous shape contracts.
