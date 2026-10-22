# e32/m4 Full5985 Integrated Source Proposal

Status: **SOURCE_ONLY_PENDING_EXACT_REVIEW; ACTUAL_COST_NOT_ADMITTED**.
One integrated candidate, no alternatives or flag search. No compiler, Host
test, reference, DUT or live-task inspection has been run for this proposal.
The previous mask-only proposal and all sealed shape contracts are unchanged.

## Files and Integration Boundary

- `case.c`: complete scalar case body, retaining original functions, RNG,
  nested history and typed fallback. Actual capacity must equal128 before
  any fixed-size setup; checks is bounded before indexing the5985-row gold.
- `fp_period.h`: eight fresh immutable uint32 input reads on every FP call,
  followed by256 ordered four-byte writes. No seed-stack-cache reuse.
- `packed_cache.h`: exact520B initialization, eight-word expected-only cache,
 65 mandatory actual reads, sticky mismatch and no early compare return.
- `gold_data.S`: data-only incbin of the already constructed exact dictionary
  and IDs, aligned8/2 respectively. It defines no instruction or helper.
- The reviewed `../full_e32_m4_mask_constant_source_proposal01/mask_constant.h`
  is included unchanged:16 clear chunks then128/64/18 ordered constant SB.
- The archived e32 `operations.h` is included by exact path. A future build
  must link the original archived `rvv_matrix_e32_m4.S` without editing it.

This is an integrated source proposal, **not a complete new firmware ELF**:
startup/linker and `replay_write` remain the mature bare-metal backend to pin
at the later admitted build stage. The original Linux syscall exit becomes
the backend return code, and tty-drain ioctl is not used. TRACE_OP0 must remain
undefined for the quoted positive cost. Existing backend behavior and endpoint
must be checked at integration; no process outcome is inferred here.

Scalar implementation changes explicitly include packed initialization and
comparison, constant-mask writes, periodic FP input setup, and bare-metal
entry/exit adaptation. Original scalar instruction identity is not claimed.
Original target/helper machine bytes must remain unchanged. No new RVV is
expressed, and future scalar auto-vectorization must remain disabled using
the established single build configuration, not a flag search.

## Tuple-by-Tuple Source Argument

The original recovered C is binary-equivalent source evidence, not original
C-byte provenance. It is bound by SHA
`7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91`.
Original e32/m4 ELF is
`4e537be1270d607f847b8c7d3d4e7be76b9b7408d184effc33a9c066cb811cf9`.
No existing original/helper/model artifact is rewritten by this proposal.

The nesting remains seed0..2, op0..34, lengths0,1,2,3,64,127,128, mode0..2,
then original kinds-dependent starts. For kinds0 the starts are0,VL/2,
and(VL<128?VL:127); other kinds retain one start0. This yields all5985 calls,
4095 integer and1890 FP, not distinct-tuple deduplication. `checks` indexes
the exact corresponding nine-ID row before its single increment. All5984
predecessors remain. Required counts are766080 results,11970 uint32 guards,
5985 returned-vstart checks and77805 original dynamic helper instructions.

Induct at the beginning of each original tuple:

1. The initial per-seed 128-step uint64 RNG and all special-case uint32
   assignments are unchanged. Previous FP writes do not leak into the next
   seed because its entire original seed loop runs again.
2. Each group has a complete128B mask clear and exactly the original selected
   store address/value/order/count. The already reviewed zero-prefix
   induction applies; there is no final-mask-only substitution.
3. If op>=25, the function loads the original eight input bit patterns during
   this call. For i=8q+r, `(i+seed)%8=(r+seed)%8` and
   `(3*i+seed)%8=(3*r+seed)%8`. The three explicit macro argument lists thus
   write the same a[i],b[i] in original order for all i0..127. Every FP call,
   including VL0, performs all256 writes. This is483840 SW and15120 input LW
   obligations; no write or required per-call input load is hoisted away.
4. All130 output uint32 words become0x0000005b via65 disjoint8B copies.
   The unchanged original helper is called with the same a,b,out+1,VL,CAP,
   mask,start tuple. The original returned-vstart failure call is unchanged.
5. Every output word is compared against the exact corresponding source gold.
   On match, `elements+=cap` equals the original128 increments. On mismatch,
   the unchanged original typed loop and guard clause run in full, with the
   original failure formatting/error count/first20 printing limit. It also
   performs the original128 element increments. Finally checks increments
   once and the next tuple starts with exactly the original logical state.

The data model already compared all778050 result/guard uint32 values and
the complete input/mask ledgers. This proposal references that unchanged
evidence; it does not turn it into candidate-C execution evidence. The FP
gold remains the640 original uint32 bit patterns, with no hostfloat or new
fflags oracle. All data bit patterns, including signed zero and NaN encodings,
are compared bitwise, not numerically approximated.

## Expected Cache and Mandatory Actual Reads

The2252 canonical64B blocks are byte-equality interned, not hash-coalesced.
Each original call retains nine uint16 IDs. Dictionary contents and IDs are
immutable RO objects, disjoint from all writable input/output/mask arrays.
Only these expected values are cached. Actual output values never enter the
cache, and no actual read is satisfied by another actual read.

`e32m4_packed_mismatch` has automatic cache variables. It unconditionally
loads ID0 and all eight expected words at entry, so no previous call's tag
or values can be reused. Each later full block loads its exact ID. If different
from the tag, it refreshes all eight expected words and assigns that new tag;
if equal, exact64B dictionary equality proves the old eight values correct.
All eight actual reads occur after either branch. The tag is neither a hash
nor a masked/truncated ID; uint16 covers every existing ID0..2251.

After block7, cache state is discarded. ID8 is loaded and only its first
expected8B is read. Actual bytes512..519 contain element127 and the rear
guard; the ROM block's remaining56 zero-padding bytes are **never** read from
the output. The first output word similarly includes the front guard and
element0. All65 actual words are compared for every tuple, including all-noop
and repeated-gold tuples. Counts from the full existing model remain:

| Event | Full5985 count |
| --- | ---: |
| Actual output8B reads | 389025 |
| Expected8B reads | 124041 |
| ID16 reads | 53865 |
| Adjacent full-block hits | 33123 |
| Full-block misses, including first fill | 14757 |
| Later full-block tag decisions | 41895 |
| Independent last-word reads, each side | 5985 |

The sticky error is initialized0 once per call. Each comparison can only
assign1, never0. There is no early return or short-circuit of subsequent
read statements. Each actual `memcpy` value is consumed by empty volatile
asm with `+r` and a memory clobber. It emits no intended hardware instruction,
but makes the read necessary even if GCC proves the mismatch already1.
The read helper cannot legally replace the value with zero or a cached value
across the intervening clobbers. All paths return only after the tail read.
Future actual-code auditing still has to prove65 reads and no extra RVV;
the source constraint is not a substitute for that audit.

A low-cost implementation can use LD then BEQ for each positive comparison,
with a single `li mismatch,1` on the unequal path, rather than XOR/OR for
every successful word. This is a constructive lowering possibility, not a
promise about GCC. Errors retain all reads and the full typed fallback;
failure-path cost is not represented as a successful run's bound.

## Aliasing, Layout and Stack

a[1024], b[1024], out[1026] remain distinct original uint32 backings. mask
remains a separate128-byte array. out and mask have explicit8B alignment.
The helper destination is still out+1 (four-byte alignment appropriate for
vle32/vse32), while scalar packed access begins at the aligned out base.
All output accesses use memcpy through character pointers, not a uint64 cast
into uint32 storage. Init/read offsets0,8,...512 cover exactly520B and fit
inside the original4104B output backing. FP writes use four-byte memcpy to
genuine uint32 arrays and preserve a[i] then b[i]; no adjacent SW combination
or alias-punning is authorized. Input table accesses remain uint32.

The expected dictionary is declared as an actual aligned uint64 array object
provided by data-only assembly; its8B reads are not a uint32 output type pun.
Its little-endian payload is bound to this little-endian RISC-V fixture.
IDs are actual uint16 data. Model proof bounds every ID; immutable pinned data
and runtime checks<5985 are prerequisites, not a waiver for a wrong ID load.
Later trace checks must compare actual ID/gold data to the immutable payload.

No restrict/pure attributes, variable-length arrays, recursion, runtime gold
construction or mutable global cache are added. Empty asm is a compiler
barrier only, not synchronization. The runtime must preserve exclusive access
to these private ordinary-RAM objects; no handler/DMA/concurrent writer may
modify mask during setup or expected ROM/output during comparison. Wrong
layout, wrong CAP, omitted clear, stale FP write, reordered SB or dropped
actual read remains a failure even if final values happen to match.

## Admission Boundary

`CONSTRUCTIVE_COST.md` derives a roughly2.84M positive instruction schedule
from this implementation's events, including control/caller/stack/runtime
allowances. It is not an old-shape relative bound, an actual GCC bound, or
measured runtime. The single proposal is eligible for independent static
review; parent authorization is still required for one Host/actualcompile
stage. Actual helper identity, no-extra-RVV, source math/fresh-write negatives,
full-read failure paths, map/stack and whole-history actual CFG cost must then
be checked. No reference or DUT is authorized here and the3M gate is unchanged.
