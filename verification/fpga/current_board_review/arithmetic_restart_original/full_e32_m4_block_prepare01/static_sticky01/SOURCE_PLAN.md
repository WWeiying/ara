# e32/m4 Single Sticky Comparator Proposal

Status: **STATIC SOURCE ONLY; not compiled, Host-run, reference-run or DUT-run.**
This directory is not included by any current build. It proposes replacement
of only `packed_cache.h` in a future independent software successor. The
software01 candidate, all failures, finish03 results and review remain sealed.

## Accepted starting evidence

`../../full_e32_m4_static_review01/SOFTWARE01_FINISH_REVIEW.json`:
SHA256 `f4a49abef6fa1512c754cfe5a3fc2cb761141ab77a376d2615d07d1d9fa071b4`,
status `ACCEPTED_CLOSED_ARTIFACT_EVIDENCE_COST_HOLD`.
The actual fixed compiled candidate's mandatory subtotal is3,283,395 (>3M),
not an RTL numerical failure. Its cache uses65 SUB,65 SNEZ,64 OR and7 ZEXT.B
per call, with48B frame/six callee-saved GPR save/restore pairs.

The exact template comes from e64/m4
`../../full_e64_m4_block_prepare01/static_sticky01/proposed_comparator.h`
and its integrated `software02/packed_output.h`: a volatile BEQ/LI asm with
read/write sticky output and memory clobber. This proposal does **not** copy
the e64 actual-output type, 66-word geometry, dictionary or noncached oracle.

## Only source delta

The complete proposed `packed_cache.h` retains the reviewed initialization,
actual8 memcpy/access barrier, gold8 memcpy, cache-fill, next-block and
function body. Only the eight repeated comparisons and the final-word
comparison call a new `E32M4_STICKY_UPDATE` macro. All eight full blocks plus
the final whole word still execute:65 comparisons,65 actual reads,520B.
No other candidate C, FP/mask header, source helper, dictionary, ledger,
flags, linker input or ABI changes are proposed.

The Host branch expands to the original C condition:
`if ((actual) != (wanted)) mismatch = 1;`.
The RV64 branch evaluates each operand once into `uint64_t` locals and uses:

```c
__asm__ volatile(
    "beq %[actual], %[wanted], 1f\n\t"
    "li %[bad], 1\n\t"
    "1:\n\t"
    : [bad] "+r" (mismatch)
    : [actual] "r" (actual_value), [wanted] "r" (wanted_value)
    : "memory");
```

Uppercase macro parameters do not replace the symbolic operand names inside
the bracket constraints. `mismatch` remains the original unsigned value,
initialized0 and only ever assigned1; no unnecessary type/ABI change.
The proposal rejects non-RV64 RISC-V compilation.

## Constraint and semantic proof

- For old sticky bit b in{0,1}, equal64-bit operands take BEQ and preserve b;
  unequal operands fall through LI and set1. The transition is exactly
  `b | (actual != wanted)`, including NaN payload and signed-zero bits.
  There is no floating comparison or signed arithmetic assumption.
- `+r` declares both the incoming and outgoing sticky value. An `=r` output
  would be wrong on the equal branch and is not used. Both input operands
  are consumed by the BEQ before the optional output write; early-clobber
  is therefore not necessary. Inputs needed after this asm remain protected
  by normal compiler liveness. No hard-coded registers or undeclared scratch
  registers are used. RISC-V has no condition-code register to clobber.
- Numeric local `1f` resolves to the label within each asm instance. It skips
  only the LI, never a subsequent read, comparison, cache refresh or fallback.
  No asm-goto or C control-flow shortcut is introduced.
- `volatile` retains every comparator asm; `memory` is a compiler barrier,
  not a hardware fence. The existing actual8 memcpy and volatile read-value
  barrier remain byte-identical. Each actual read is computed even after b=1;
  no `&&`, `||`, early return or mismatch-dependent read qualification exists.
- Memory remains accessed via memcpy/unsigned-char addressing. There is no
  uint64_t pointer punning of the uint32_t output, alignment assumption added
  to the C interface, alias cast, out-of-bounds access or shift. Loads cover
  offsets0,8,...,512 of the exact520B: first word includes front32-bit guard
  and result0; last includes result127 and rear32-bit guard. No padded tail.
- The first block always fills c0..c7 and tag on every call. Each next block
  compares its immutable16-bit ID to the prior tag; mismatch refills all8
  expected words before use, equal ID reuses identical values. The comparator
  does not assign tag, IDs or cache values. The final ID loads one expected
  word only, independently of the eight-word cache. No cache survives a call.
- The asm memory clobber cannot change a C local's value. It may affect GCC
  allocation or scheduling, so actual expected loads, spills and callee saves
  must be audited after an authorized compile; source proof does not assert
  the old48B frame will necessarily remain the generated frame.
- Original failure handling is untouched: a mismatch returns to the complete
  original per-element/guard fallback; all65 packed reads have already occurred.
  Multiple failures cannot reset sticky state. Original error counts and
  source vstart/data/guard oracles remain; no fflags oracle is invented.

## Full-history obligations retained

Source-derived CAP128/SEW32/LMUL4,35ops,5985 calls in original3-seed order;
766080 results,11970 guards,5985 vstart returns,77805 helper instructions.
The458 static original helper instructions/1688B stay unchanged. FP640-word
expected bit patterns/RNG/gather boundaries/fallback are not recalculated.

The comparator update leaves these mandatory event counts intact:

| Event | Whole5985 history |
| --- | ---: |
| Actual output LD | 389025 |
| Expected dictionary LD under original cache contract | 124041 |
| ID LHU | 53865 |
| Same-ID adjacent hit / full-block miss | 33123 /14757 |
| Output initialization SD | 389025 |
| FP input SW,256 per FP call in a[i],b[i] order | 483840 |
| Mask zero SD,16 before selected writes per group | 35280 |
| Ordered cumulative selected-mask SB | 154350 |

FP fresh8 input loads per1890 FP call, all per-call SW,128B mask clearing and
selected SB order are byte-identical source obligations. This new shape uses
the already-reviewed constant SB sequence, not an obsolete selected-mask LBU
requirement. No callback to older e32/m2 or e64/m4 contracts is modified.

## Cost hypothesis, not GCC evidence

The shorthand potential `2*65*5985=778050` treats every old comparison as
three instructions. Actual software01 has only64 OR, so the conservative
comparison-only difference is `(65+65+64-65)*5985 = 772065`.
Retain all old7 ZEXT.B, all35,910 ABI SD plus35,910 ABI LD, frame adjustments,
cache/tag/ID traffic, initialization, FP/mask, caller and stack costs until
the actual new ELF proves their replacement. No presumed callee-save removal
is included in this hypothesis.

If every other old mandatory instruction remained unchanged, that subtotal
would be3,283,395-772,065 = **2,511,330**. It is **not** a whole-program upper
bound. The3M budget would leave488,670 for all omitted main/RNG/startup/call
costs plus any new allocation overhead. The prior2,845,347 constructive
schedule is not reused as a GCC prediction. No run-time or reference guarantee.

## Next gate (not performed here)

Hilbert reviews this exact header, delta and proof first. Only subsequently
authorized fixed-flag compilation may decide feasibility. It must retain the
old source bytes except this comparator, reconstruct all hit/miss/error paths,
65 actual loads even after error, cache reset/tag integrity, all FP/mask
events, helper bytes/no extra RVV/CSR/fence, exact520B bounds and64KiB stack.
All additional moves, spills, saved registers and caller paths count toward
the whole CFG <=3M gate. If the unique candidate exceeds it, HOLD; do not
compile another variant or use a long reference to discover cost. No Spike
or DUT is authorized by this static proposal.
