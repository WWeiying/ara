# Original Fixed e8/m4 Full10752: Static Cost Plan

Decision: **SOURCE_EQUIVALENT_OPTIMIZATION_POSSIBLE_COST_UNPROVEN**.
This is one static source proposal for a future parent decision, not compiled
software, a Host/reference pass or DUT admission. No equivalent existing full10752
plan/acceptance was found in the fixed_restart_original Markdown inventory;
the accepted full777 is only the first777 calls of this parent.

## Source Identity And Exact Scope

Canonical evidence is `../recovery01/{report.json,successor_oracle.c,scenario.S,
operations.h}`. The archived and rebuilt original ELF both hash to
`ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc`.
Recovered C hashes to `ab82b4891f9e926e37ef4d9f10fc44b0f953136deef2173b84427c0447e81006`;
this is a binary-equivalent reconstruction, not recovery of missing historical
C text bytes. The original assembly matches the archived assembly exactly.
Exact current input bindings, including the accepted prefix's actual disassembly
and reference/terminal metadata, are in INPUT_PINS.json. No large raw was read.

operations.h:1-14 selects four operators in order: vsmul.vv,vsadd.vv,vsaddu.vv,
vssub.vv; all kinds=4,INTEGER_EXTENSION=1,AGNOSTIC_POLICY=0,RESTART_SUITE=1.
The original compile defines SEW=8,FRACTIONAL_SUITE=1, not FIXED_SCALAR_SUITE,
UNMASKED_SUITE or MACC_ACCUMULATORS. Source lines239-405 establish:

- VLENB128 implies CAP512,physical group4,e8/m4,vtype2,tu/mu. Preserve capacity
  and vlenb checks; max_start=1023. VL order is0,1,2,3,256,511,512.
- Loop order: seed0..2,op0..3,VL slot0..6,mask mode0..3,si0..3,control0..7.
  Starts are1,VL/2,VL,511, including duplicates. Control selects vxrm=control&3
  and initial vxsat=control>>2. No tuple/RNG/helper call may be deduplicated.
- Total3*4*7*4*4*8=10752 calls;5505024 result bytes and21504 guard checks.
  All four24-instruction helpers remain byte-identical:258048 dynamic helper
  instructions plus capacity3; static helper total99. Required memory helpers
  are5 per call,53760 in total, even when the target has no active elements.
- Inputs a[1024],b[1024],out[1026],mask[128] retain original backing. Only the
  first512 source elements are initialized each seed. out+1 stays the helper
  argument; scalar output footprint is exactly514 bytes, not a rounded520.
  mask is physically128 bytes although vlm.v at capacity512 consumes64 bytes.
- Original28 TRACE_RESTART_BOUNDARIES records remain in their original places.
  Any bare-metal runtime adaptation must explicitly retain the established
  source-port/Linux tty-drain limitation, not claim original Linux replay.

## Exact Loop And Byte Counts

These counts follow the source loop bounds, not a new numerical oracle run.

| Source operation | Full-parent count | Obligation / candidate representation |
| --- | ---: | --- |
| xorshift input iterations |1536|All3*512 iterations, original state sequence and special-value overrides |
| Input SB including overrides |4416|1472 per seed; retain order, including overwritten random values |
| Mask construction epochs |336|One per seed/op/VL/mode, then32 calls share that mask |
| Original mask-clear SB |43008|128 bytes each epoch; candidate16 exact scalar zero SD/epoch=5376 |
| Original selected mask SB |70644|84*(512+256+73+0), preserve every cumulative value/address/order |
| Original two output-init loops |11031552 byte writes|10752*(514+512); both produce0x5b with no intervening observer |
| Fresh output bytes after merging duplicate init |5526528|514*10752, every call still initializes all output and guards |
| Candidate output init |698880 stores|64 aligned SD+one SH at offset512 per call |
| Candidate actual output read |698880 loads|64 aligned LD+one LHU at offset512 per call, all paths |
| Original per-element expected comparisons |5505024|All512 byte results remain checked exactly by packed equality |
| Active element evaluations |303744|Source-qualified i in[start,VL), selected(mode,i); not a license to skip inactive checks |
| Calls with any source-active element |2976|Remaining7776 have a completely sentinel expected output |
| Target vstart<VL calls |4608|Not2976: predicate-alloff does not waive nonempty backend ownership |
| Returned vstart / saturation checks |10752 each|Entire low32 and entire high32 status, not just one saturation bit |
| Saved CSR restore operands |21504|Both vxrm and vxsat each call; no invented final readback |

The output's first LD contains the front guard and results0..6. Its last LHU
contains result511 and the rear guard. Bytes514..1025 stay outside the per-call
output footprint. No scalar access may overrun the514-byte initialized region.

## Why Reusing Full777 Unchanged Cannot Meet3M

The existing optimized SoC disassembly has a3-instruction init loop at
0x8000008c..0x80000090, repeated64 times, and a7-instruction passing comparison
loop at0x800000da..0x800000f0, repeated64 times. Merely repeating those two
loops10752 times costs6881280 instructions before tails, helpers, caller or mask.
Actual old full_init is202 instructions/call; full_oracle's equal path is473.
Those concrete functions alone would cost7257600 for10752 invocations.
The measured790055/777 reference is a prefix measurement, not a full-parent bound.

Even fully unrolling ordinary paired actual/expected reads cannot solve it:
65 init stores +65 actual loads +65 expected loads +65 equality branches +24
original helper instructions gives284*10752=3053568 instructions, already over3M.
This is a lower floor for that specific implementation class, not a universal
lower bound on every possible exact scalar oracle.

## One Candidate: Sentinel Row Then Exact Block Dictionary

Use a uint16 row-ID per call, a row descriptor containing9 uint16 block IDs,
and a value-deduplicated64-byte immutable pool. Keep expected saturation in a
separate per-call byte; equal output rows must not merge sticky/CSR expectations.
The first8 block slots cover512 actual bytes; the ninth covers only2 actual bytes.
ROM padding is representational and never authorizes a full tail LD/SD.

Reserve row0 for the exact all0x5b514-byte expected output. It takes a constant
comparison path, not a skipped call or shortened check: execute all24 helper
instructions and then every64 LD+LHU. Other rows process all9 block descriptors;
known-sentinel blocks compare actual values to the constant without an expected
LD. Non-sentinel blocks load their exact8 expected words, or one low16 tail value.
No actual result, input, helper, CSR, output initialization or mask write is cached.

This does not assume that an active computed value is rarely/usually0x5b.
GEOMETRY.md gives a symbolic upper bound using only original active ranges and
the proven operator dependence on rounding: at most442 row descriptors and716
blocks, including distinct padded full/tail sentinel blocks. Value dedup can only
reduce these counts. A row-ID array, descriptors, pool and saturation bytes need
at most86036 bytes, before alignment and any added caller metadata. Full flat
65-word tables would need5591040 bytes, which does not fit1MiB.

Use scalar memcpy for fixed8-byte and2-byte loads/stores to avoid alias punning.
The real out backing is aligned8; keep out+1 for the original helper. Unroll the
64 initialization SD and the8*8 comparisons, with a separate LHU tail. Positive
comparison lowering needs a single equality branch per actual word, not a
SUB/SNEZ/OR triplet. A sticky mismatch must not bypass later actual reads.
This is a source proposal; GCC lowering and register allocation remain unmeasured.

Mask construction should keep all70644 selected SB, but use source-derived
constant cumulative values in original selected-i order after the16 zero SD.
No concurrent writer exists between clear and bitset. Therefore replacing the
redundant LBU/OR with the exact cumulative byte is mathematically valid. This
changes scalar instructions, not original vector helper identity. A compiler
memory barrier between writes may preserve each distinct store without hardware
fences. Mode0 has8 reusable cumulative constants, mode1 has4, mode2 has8; do not
assume GCC will retain these in registers. A source-qualified selected sequence
also removes the512-iteration scan of unselected positions; it does not remove
any original store. Mode3 still clears all128 bytes and executes its32 calls.

## Preserve The Original Error Oracle, Not Just PASS

The prefix's prepare.py:125-130 replaces an arbitrary number of byte mismatches
with one generic failure. That existing accepted prefix is not reclassified, but
this is **not** an adequate template for the requested full-parent error-count
contract. On packed mismatch, run the untouched original per-element scalar
oracle/failure loop over the already produced output, without reexecuting the
vector helper or reinitializing output. Preserve individual error increments,
first20 diagnostic suppression, full elements/checks totals, vstart-before-data,
saturation-after-data and the single combined guard failure in source order.
The original combined guard diagnostic reports out[cap+1] even if only the front
guard is wrong; do not silently substitute a different diagnostic convention.

Expected values must come from the original signed/unsigned saturation and
rounded() semantics for all4 rounding modes and both sticky inputs. No hostfloat,
hash-only oracle, relaxed tail or finalmask-only substitute is proposed. Preserve
the original RISC-V GCC signed conversion/right-shift implementation choices;
new memcpy indices have fixed valid bounds, no type-punning or shift-by64.

## Constructive Cost, Not A GCC Upper Bound

| Component of proposed positive path | Instructions |
| --- | ---: |
| Fresh65 stores +actual65 reads +65 equality branches +helper24, all calls |2354688|
| Non-sentinel expected loads, using geometry only |<=81216|
| One row-ID load and row-zero branch/call |21504|
|9 ID loads/branches for2976 non-sentinel rows |53568|
| Two address instructions/non-sentinel block |21312|
| Two row-descriptor address instructions/non-sentinel call |5952|
| Subtotal before masks/RNG/caller/setup |2538240|
| Mask16SD clear/epoch plus conservative LI+SB per selected byte |146664|
| RNG six shift/XOR ops/iteration plus all4416 input SB |13632|
| Accounted subtotal |2698536|

This leaves only301464 instructions,28.04/call, for **all** uncharged work:
caller arguments/call/return, init/oracle entry and pointer/constant setup,
vstart/saturation checking, counters, remaining RNG branches/overrides, group
loop control, ABI spills, BSS,28 trace records and exit. Branch placement/join
instructions also need charging. The two-instruction descriptor address entry
is constructive, not a promise that GCC uses it. The actual old caller slice
0x80000532..0x800005ec alone has37 positive instructions, before start selection
and other overhead, so preserving it verbatim cannot fit this estimate.

Reusing the8/4/8 mask constants rather than materializing every selected byte
could reduce the mask term by68964 instructions, leaving370428,34.45/call, still
not a complete bound. It is part of this one candidate's scalar lowering opportunity,
not permission to try many compiler variants. Hoist start calculation outside
the8-control loop, keep counters/pointers in locals where safe, and avoid generic
per-call tuple re-decoding; preserve original loop order and every side effect.
Whether ordinary C achieves the remaining caller budget is the key unresolved
question. No claimed hand-lowered sum is an actual compiled PASS.

Conclusion: memory is comfortably feasible; source mathematics permits a
plausible path below3M, but the present evidence does not prove it. Recommend
only parent-authorized source integration and independent source/equivalence
review next, then one fixed-flags actual compile/CFG gate if separately approved.
If complete positive-path CFG exceeds3M, HOLD before reference rather than trying
a longer reference or deleting calls. Preserve the64KiB stack reservation in the
future actual map; old prefix frame208 is not a bound on a new compiler frame.

The full777 actual M8 run was2203.943844s, not a10752-call runtime measurement.
Even a future <=3M firmware result does not establish a<=3h full DUT bound:
53760 full-capacity memory helpers remain,13.84 times the prefix's3885. Runtime
admission must separately charge their actual completion cost. No new simulation
is recommended or authorized by this static report.
