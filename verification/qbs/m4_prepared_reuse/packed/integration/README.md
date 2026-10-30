# Combined M4 preparation integration

This directory stages the production delta without editing the live runtime or
the sources of the complete Q/V/K VCS measurement. The normal library rebuild
and installed-model gate remain required before promotion is accepted.

## Dispatch contract

- The existing `GGML_RISCV_QBS_M4_PREPARE=1` switch remains necessary.
- `GGML_RISCV_QBS_M4_PACKED=1` chooses the shared packed producer. Otherwise
  the existing producer remains selected; no default is changed.
- Both direct four-row preparation and cache misses call the same shared
  `selected_quantize()`. Cache identity uses producer tag 1 for the old
  producer and 2 for packed. Exact owned input comparison and raised-FFLAGS
  replay are unchanged. A cache hit does not execute the quantizer.
- Existing shape, thread, graph/epoch, numerical-domain and cache-size limits
  remain. Strided inputs cannot enter this cache. A producer's `false` result
  means generic output was already produced, not that preparation failed.
- The accepted blockwise gather fixes QBS four-row, tail and wide-M input
  views. The helper is copied unchanged; the dense preparation path does not
  perform this gather. Ordinary RVV repack view handling still needs its own
  reproduced case and repair before this is a complete fallback integration.

The new `GGML_RISCV_QBS_M4_SELECTED` record uses `source=direct` or
`source=cache`. `tag` identifies the selected producer, not the executed
algorithm. Thus `tag=2 path=generic` is a legitimate generic fallback;
`tag=2 event=hit` means cached bytes were copied. Tag 0 means M4 preparation
was disabled. Existing preparation and cache trace records are unchanged.

## Completed checks

`m4-packed-integration-stage-20261027-01` compiled the combined integration
object with the normal production command. A separate QBS-disabled syntax
check passed, but that is not an execution test of ordinary RVV fallback.

`m4-packed-integration-graph-20261027-01` passed 24 real GGML graph executions.
The old producer/cache-off control and packed/cache-on candidate have identical
output and CSR bytes: 46272 paired bytes. Scenarios include adjacent consumers,
intervening float work, in-place input changes, a custom writer, two workers,
different input values at the same address across graph epochs, and non-RNE
rounding fallback. The link map binds the Q4_K integration implementation and
repack buffer entry point to the staged object; ordinary libraries supply the
remaining runtime. This is private-object functional evidence, not a normal
installed-runtime or hardware-speed result.

| Mode | Direct RVV preparations | Direct generic preparations | Cache computations | Cache hits |
| --- | ---: | ---: | ---: | ---: |
| Old producer, cache off | 60 | 12 | 0 | 0 |
| Packed producer, cache on | 36 | 12 | 12 | 12 |

Graph log SHA-256:
`08b7abcd86a6c02c78da9767b54a5aa0ed78cf2c49a86bcd0c2811781a7cc13b`.

## Source-identity guard

Review found that the sealed staging implementation samples extra input hashes
with `dict.update`, which can overwrite an inherited expected hash. It is
retained unchanged because the completed compile/graph evidence pins it.
Current acceptance therefore requires the independent `guard.py` audit. It
uses fixed accepted-manifest digests, rejects conflicting expected hashes
before merging, checks all files, and replays the raw graph and link evidence.
An overwritten pin cannot pass merely because the file was later restored.

`m4-packed-integration-audit-20261027-01` passes: 1980 accepted prerequisite
entries, 2007 combined input files, no conflicting hashes, and independent raw
graph/link replay. Seven guard tests include rejecting changed producer tags,
missing selection records, and confusing cache hits or fallback with execution.

For a fresh staged build use `prepare.py`, which validates the accepted inputs
before running the sealed builder and audits its recorded inputs afterwards.
Do not use a `COMPILE_ONLY_PASS` staging report alone as promotion evidence.

```sh
python3 -B verification/qbs/m4_prepared_reuse/packed/integration/prepare.py \
  --output verification/out/NEW_PACKED_INTEGRATION_STAGE
python3 -B verification/qbs/m4_prepared_reuse/packed/integration/run_graph.py \
  --candidate verification/out/NEW_PACKED_INTEGRATION_STAGE \
  --output verification/out/NEW_PACKED_INTEGRATION_GRAPH
python3 -B verification/qbs/m4_prepared_reuse/packed/integration/guard.py \
  --candidate verification/out/NEW_PACKED_INTEGRATION_STAGE \
  --graph verification/out/NEW_PACKED_INTEGRATION_GRAPH \
  --output verification/out/NEW_PACKED_INTEGRATION_AUDIT
```

These are intentionally baseline-bound migration checks. Changed runtime or
accepted-source identities must be reviewed before creating a successor; do
not refresh expected hashes to make the checks pass. No RTL, live library,
model cache or source-pinned VCS experiment is modified by these commands.
