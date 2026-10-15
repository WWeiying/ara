# e8/mf4 M9 Terminal Review

Decision: **ACCEPTED**, metadata-only independent terminal review of
`full_e8_mf4_o2_vcs_m9_successor02/prepared01`.

## Exact Scope

- One continuous original e8/mf4 cap32 program: 4095 calls, 131040 result
  elements, 8190 guards, 4095 returned-vstart checks, 53235 helper instructions.
- Full ordering retained, no partition reset. This is not e8/m4, all22 shapes,
  original Linux execution, or proof of the historical Linux stall mechanism.
- Original source has no explicit fflags oracle; none is claimed here.
- Strict/generic reports agree: 4627616 rows, 4446338 retired instructions,
  last cycle6771285; generic VALID, zero CVX exceptions.
- 20475 compulsory memory-helper owners plus117 nonempty op24 memory targets
  equals20592 required memory owners. The117 predicate is vstart<vl, not mask
  population. This is not an all-arithmetic-target minimum-owner claim.
  Actual total alloc/done23067/23067, live owners0.

## Actual Completion

- Durable simulator child rc0,7872.941444882192s; no timeout/failure/cancel.
- Producer full PASS, no abort, retries0; runner COMPLETE and exact one-item
  summary agree with durable numeric outcome and command/privateELF identity.
- The launched service explicitly installed ExecStopPost. Its recorded actual
  environment is success/exited/0, hook PID2966627. No GC/default-property or
  missing-process inference was used.
- Collector PID2966628 actual wait rc0,26.006832502782345s, no timeout; its
  result is PASS_FULL4095_M9_METADATA_COLLECTED_NOT_LINUX.

## Evidence Binding

- Plan: `57d3d71260ae7b06f2bd6498ab9246bf1e4cbc9146935a916bc6d39ca9139ca8`
- Complete: `1d1a5288221e5d4310bea98c973688bfda1f8c09abfbb2214f80eda971fca471`
- Collector result: `dfd8884901dcb68041e0cfd361793405cd44bf92c62cfc515f20b0fc8b2caaa4`
- Collector exit: `bcd98102b4c540adfa2195dba78abc78184b2e6b30d03e43016d99dafda9efca`
- SoC ELF: `33fac90cb3c541657ede2d3b01e2cbd52d7ddd97cd0b78599ac237f237c16f44`

The896 input pins match the entry-review map. Their terminal unchanged status
is inherited from the completed producer/collector verification, not claimed
as a new full rehash. Eleven of12 small execution evidence files were freshly
hashed and compared. The CSV digest is cross-bound between producer and
collector without reading or hashing the CSV again. M9 image identity is
cross-bound through plan, entry, command and input image-hash map.

Collector code is transitively pinned: plan-pinned exit_hook.py checks its
hardcoded SHA before execution; the actual wait receipt records the same SHA.
It is not a direct collect.py entry in the plan pin map. An initial local
metadata assertion assumed that direct key and stopped with KeyError; checking
the actual hook contract resolved this without editing any producer artifact.

`result.json` binds the small metadata files and records the successful local
metadata check's actual exit0. No new simulation, Host/reference execution,
CSV semantic parse, large-file hash, or live-systemd query was performed.
Historical HOLD and earlier failures remain unchanged.
