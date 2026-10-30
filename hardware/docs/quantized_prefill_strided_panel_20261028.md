# Bounded strided-K panel reuse for causal query groups

The running native experiment uses contiguous captured K rows. Before
production integration, the same scheduling idea must also handle a KV view
whose row stride exceeds its stored row size. The current Decode panel cache
uses an exact token-count key. Prefill rows with different visible prefixes
could therefore copy overlapping K rows repeatedly within one tile.

The experimental `prefix_panel.h` adapter gathers the union of the group's
visible prefixes once per tile, into the same bounded size of panel: at most
32 rows, each at most 272 bytes. QBS commands still request only the score
elements visible to their query rows. The panel contains real rows used by at
least one query, not globally masked padding. Contiguous K bypasses gathering.

This changes software scheduling and workspace use, not hardware storage or
the QBS instruction interface. The adapter delegates descriptor construction
and activation alignment to the existing native bridge. Its context is private
to one pre-admitted group; the input allocation and its contents must remain
unchanged until execution completes. It is synchronous, not thread-shared.

The union length is computed from validated positive per-row prefixes. A tile
beginning at or beyond a row's prefix cannot submit that row. Invalid requests
are rejected before gathering. For a gathered command, panel-relative metadata
is installed temporarily and restored on both success and executor failure.
It must not survive past the synchronous call as a borrowed pointer.

## Checks

```sh
python3 verification/akv/quantized_kv/prefill/test_prefix_panel.py
```

GCC and Clang UBSan each pass 24 combinations: D=32/96/128, Q4_0/Q8_0 keys,
and four patterns containing prefixes from 1 to 65. Each runs both contiguous
and padded-stride inputs. The executor checks actual gathered bytes against
the original strided rows before invoking the QBS numerical reference.

Checks include bit-exact outputs, untouched padding, zero contiguous copies,
one panel per visible tile, copied bytes equal to maximum visible prefix times
row size, no command for a masked request, and context restoration after an
injected executor failure. These are functional checks, not VCS performance
measurements. Full-call admission, real strided capture evaluation and runtime
dispatch integration are still required before enabling this path in GGML.
