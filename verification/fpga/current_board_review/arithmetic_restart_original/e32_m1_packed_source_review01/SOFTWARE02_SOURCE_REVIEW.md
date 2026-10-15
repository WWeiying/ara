# Software02 Mask Clear Source Entry

Verdict: **SOURCE NO_BLOCKER for the single authorized Host/compile attempt**.
No reference or DUT authorization. No compilation, Host test, reference or DUT
was run by this review. The prior software01 cost HOLD remains unchanged.

Reviewed producer files under `full_e32_m1_packed_prepare01/software02/`:

| File | SHA256 |
|---|---|
| case.c | `e8a642c360cb7bac3c638f5f0b6f29ac5bad60f2a485d108b7030609764960c4` |
| mask_clear.h | `96927c638459143ecca3e948a2644f7e14c127baed98906e31b292b37268ac9e` |
| SOURCE_PLAN.md | `7c9ae455bf189818a6729f8dc855977df70bc23b9d110d03a583702b4e9a5ca0` |

Independent reverse-diff check restored exactly software01/case.c, SHA
`fec8ad945ff747957984e657bf912ca9af4251b40047d514c04879911f47f6fa`:
only the header include and replacement of the128-byte zero loop differ.
Original selected-bit construction, every FP call's32 pairs of input writes,
next-seed RNG,5985-call order,35 operations, packed oracle and original fallback
are unchanged. Original FP table/helper identity remains a build-artifact gate.

## Lowering and Semantics

The header uses a local uint64_t zero and16 fixed8-byte builtin memcpy accesses
through unsigned-char offsets0,8,...,120. Their disjoint union is exactly the
128-byte mask object. There is no uint64_t pointer dereference, alias violation,
alignment assertion, overrun, or rounding of the footprint. Endianness is
irrelevant to an all-zero representation. All2205 mask groups still clear the
entire object before the original32-position selected-bit loop, including the
upper124 bytes not consumed by the four-byte architectural mask load.

Every memcpy is followed by empty volatile asm with a memory clobber. These
compiler-visible boundaries prevent merging the separate writes across the
boundaries into a single whole-object zeroing operation. The asm template emits
no target instruction and is not a hardware fence. It does not change the real
memory contents or RNG/register history seen by the original helper. This is
the reviewed sole candidate; no alternate opacity strategy is requested.

Source form alone does **not** prove sixteen SD instructions: target alignment,
individual memcpy lowering, register allocation/spills and compiler placement
still require inspection. Keep the proposed actual-artifact gates: mask address
8-byte aligned in both linked ELFs, exactly16 scalar8-byte stores covering0..127
at each real mask-group entry, no initialization call/byte loop/extra RVV, and
unchanged selected-bit ordering. A failed lowering is HOLD, not permission to
try additional variants or compiler flags.

## Single Attempt Gates

Reuse the12 pinned software01 original Host logs as baseline, compare all12 new
packed outcomes, retain both missing-equal-valued FP-write rejections, and check
dirty full128-byte clear with unaligned/protected-edge Host buffers. The helper
must also overwrite every byte even when its initial value was already zero.
Recheck actual458 original helper instructions, full136-byte output and all
191520 data/11970 guard checks,1890 per-call FP refresh loops, original exact-bit
table, noextraRVV and64KiB map/stack reserve. Host success is not reference PASS.

Recompute the complete positive-path compiled CFG with new PCs and all changed
setup/spill/control overhead. The nominal811440-instruction store-loop saving
is only a source estimate, not a measured saving or a copied cost verdict.
Even an actual upper bound <=3M requires the parent's separate finite-reference
admission; >3M or an unbounded accounting gap remains HOLD. No reference/DUT is
admitted by this source review.

Read-only tool completion `93ba72`, numeric0, verified the reverse diff, exactly16
memcpy/barrier pairs and exact footprint; it is not a Host or compiler receipt.
