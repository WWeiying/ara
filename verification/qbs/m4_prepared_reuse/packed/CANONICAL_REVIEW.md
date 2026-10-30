# Shared packed producer: staged, not installed

`software/qbs/ggml/q8_K-m4-packed.h` is the shared implementation prepared for
benchmark and GGML use. It depends only on the existing canonical numerical
helpers, not on verification prototypes or the rejected segment-store code.
The current live runtime and source-pinned complete-call experiment are not
changed by adding this unreferenced header.

## Gate

`verification/out/m4-packed-canonical-20261027-02`: **PASS**.
Result SHA-256:
`6043338ab4c2e9f422e86f484fc966799355df8b8a0f1a40099657ef75c55daf`.

The existing extent test object is linked against the new shared producer;
the original RVV producer and production generic remain unchanged. Four VLENs
each pass 576 complete byte/state/guard comparisons and 28 nonfinite admission
checks. The parent independently verifies every retained input/artifact hash.
These are functional QEMU results, not additional hardware timing results.

Both producer objects contain 407 instructions. The raw opcode comparison
initially rejected the copy because the `__assert_fail` line-number argument
changed from 26 to 49. This changes one `li a2` encoding in the terminal failure
block, not a calculation or valid-input control path. The failed first gate is
preserved at `m4-packed-canonical-20261027-01`.

The revised gate permits only that explicitly checked diagnostic difference:
the immediate must equal the unique assertion's actual source line, be in the
terminal assertion block, and feed the `__assert_fail` relocation without
intervening arithmetic or argument replacement. All remaining raw opcodes must
match. Five checker tests include rejection of changed arithmetic, argument,
call target, and nonterminal work. The report deliberately says
`object_instructions_equal=false`; this is not formal linked-binary equivalence
or proof of identical runtime performance.

## Integration contract

- `quantize()` has the original four contiguous rows, aligned nonoverlapping
  buffer and K-multiple-of-256 contract. Its `false` return means the generic
  fallback already produced the output, not that the output is missing.
- `GGML_RISCV_QBS_M4_PACKED=1` selects the packed producer. Other values leave
  the existing strided producer selected. The choice is process-stable.
- Callers must still enforce the existing M4-preparation enable switch and
  runtime shape/layout policy. Adding the helper does not make strided views
  contiguous or change cache admission.
- `selected_quantize()` is intended for both direct preparation and cache
  misses. `producer_tag()` returns 1 for the original and 2 for packed so that
  persistent prepared-byte entries have an explicit producer identity.
- The opt-in selector, cache integration, actual installed graphs and model
  execution still require their normal-runtime gate. No existing call site has
  been switched in this commit, and there is no new default enablement.

```sh
python3 -m unittest discover \
  -s verification/qbs/m4_prepared_reuse/packed -p test_codegen.py
python3 verification/qbs/m4_prepared_reuse/packed/run_canonical.py \
  --output verification/out/NEW_CANONICAL_PACKED_GATE
```
