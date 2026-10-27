# Packed-word preparation candidate

This successor addresses the measured segment-store expansion without changing
general RVV/Linux memory semantics. It is not installed in the runtime.

The rejected predecessor emitted 72 architectural four-field stores and caused
36864 single-element storage allocations, plus 72 layout operations. The new
candidate retains its encoding, grouping, slide/reduction and fallback logic,
but zero-extends the four signed-byte bit patterns and constructs
`row0 | row1<<8 | row2<<16 | row3<<24`. Ordinary e32/m4 unit-stride stores emit
those words in the existing little-endian four-row byte layout. Zero extension
is essential: sign extension would corrupt neighboring row fields.

The existing naturally aligned block/payload layout is statically checked.
GNU/Clang's alias-qualified word type is used for the byte payload; no new
compiler flag weakens alias analysis globally. This prototype assumes the
existing aligned, nonoverlapping buffer contract. A big-endian build retains
the generic fallback. Production promotion requires reviewing the supported
compiler contract, not just a successful build on this machine.

The generated machine code is checked before timing: ordinary `vse32` must be
present, segment instructions absent, and no whole-register vector spills may
appear in the candidate body. This removes a demonstrated bad mapping but
does not prove a net gain: widening, shifts, ORs, slides/reductions and register
layout work still cost cycles. Reject it if complete measurements regress.

## Functional gate

`verification/out/m4-packed-reference-20261027-01` is PASS. The exact existing
808-case comparison is retained, changing only the candidate function symbol
and printed labels. Three real groups, generated zero/tie/signed-zero/finite
cases, all sticky-flag and VCSR combinations for the real groups, non-RNE
fallback, full output bytes, guards and generated-input integrity are checked.
All 808 cases pass at each of VLEN128/256/512/1024. QEMU measures no cycles.

## Independent RTL pair

```sh
python3 verification/qbs/m4_prepared_reuse/packed/build.py \
  --output verification/out/NEW_PACKED_BUILD
python3 verification/qbs/m4_prepared_reuse/packed/run.py \
  --build verification/out/NEW_PACKED_BUILD \
  --output verification/out/NEW_PREFLIGHT
```

After review, use another fresh output and `--execute-reviewed` in a direct-owned
background service. The worker uses the unchanged canonical VCS image and all
existing protocol checks, with a three-hour bound. Two affected objects are
rebuilt; nine unchanged objects are reused only after checking the complete
original source/object manifest. The same ELF runs original/packed/packed/
original, three actual preparations per trial. Full fixed-golden bytes, caller
CSR state, canaries and input-copy integrity must pass. The checker rejects
custom accelerator or segment work in the vector allocation trace.

This isolates preparation. Even if it improves, it still needs complete-call
timing and actual GGML/model acceptance before backend integration. The prior
25.09% complete Q/V/K reuse gain remains separate and is not multiplied by a
preparation-only speedup. No RTL, physical implementation or runtime default
is changed here.
