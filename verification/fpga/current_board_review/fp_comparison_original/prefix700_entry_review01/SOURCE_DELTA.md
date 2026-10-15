# Prefix700 Source Delta Review

Status: STATIC_SOURCE_DELTA_NO_BLOCKER, final reference/worker entry pending.
This is not a DUT acceptance or launch binding. No reference/Host/compiler/DUT
execution or raw CSV/reference parsing was performed by this reviewer.

Inspected actual generated files in `../full700_m9_prepare01/prepared01/`:

- `case.c` equals sealed packed682 source with exactly one entry-name and one
  `if(cases==682)` substitution. `original_source_port.c` has the same exact
  two substitutions relative to its original scalar port. No other source delta.
- Sealed `host.c` contains exactly two `682` occurrences (stop/assert), one
  `698368`, and one `11173888`. Generated `host_exhaustive.c` exactly matches
  these replacements with700/716800/11468800. No data/fixture constant was hit.
- `host_flow.c` differs only by name, one calls-bound substitution, and the
  explicit final-call mutations for NV, active result bit, guard and vstart.
- Parsed both actual C table initializers: all five input ROM rows are equal;
  all first682 packed records, including input selectors, flags and complete
  zero/one allowed-bit masks, are value-identical. New table has700 records;
  endpoint is seed1/op2/VL3/mode1/sticky1/flags1.
- New model retains the independent integer FP16 comparator and original
  unmasked oracle: active exact bit; VL0 old bit; other tails allow old/1/fixture
  result. It does not substitute mask-off semantics or blanket-one tails.
- Observed Host exhaustive log reports700 calls,716800 input halfwords,
  11468800 exhaustive byte alternatives and700 flag checks. This is producer
  Host evidence, not a repeated independent Host execution.

Actual ELF verification, not solely disassembly text comparison:

| Artifact | SHA256 |
| --- | --- |
| prepared01/soc.elf | 3ba16b09e650fdb16ad5e65027051fbed47c032e3883f80bfb0eae39fbcb1388 |
| prepared01/spike.elf | 167b4df0ebcd3b435c615b9896daef476ca751bb8936c7b3cd6ef7eb81aa754e |
| Original archived parent ELF | 266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754 |

Both actual ELF PT_LOAD contents match all193 helper instructions (capacity3,
four16-instruction vv helpers, six21-instruction vf helpers). Their encodings
match sealed682 disassembly, and each complete helper byte sequence occurs
exactly once in the original archived ELF. Target op2 is PC0x8000077c,
encoding6e881457 in both new ELFs. Scalar addresses are allowed to relocate;
the future checker must use each actual ELF spec rather than old literal PCs.

Reviewer diagnostic retained: the first read-only helper audit stopped with
KeyError `capacity` because original `archive_dis.log` has only a stripped
`.text` symbol. Earlier source/table assertions had passed. A separate bounded
static byte check used actual original ELF sequence matching, without inventing
symbols or changing any producer artifact, and exited0 (386 instruction checks).
This was an audit-script assumption error, not a software/reference/DUT failure.

Additional original report independently checked:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_compare_uncovered01/original_board_report.json`,
SHA256 `7ed11ee7257c8571d8d5d4bf87780231d82fd5373173343598d21d47ed5aa00f`.
Actual schema is `report.results`; this parent's20 retained ordinals are
50 and681..699, full summary errors1252. Together with independently checked
scene11 ordinals681..700/errors1472, the union contains21 distinct retained
positions with maximum700. Error totals from the two executions are not added.

Final entry still requires sealed READY, actual full700 reference audit and
wait receipts, fresh pins, and reviewed worker/plan. Required scope is700 calls,
699 predecessors,358400 result bits,1400 guards,700 flags/vstarts,12880 helper
instructions. The observed Spike process exit0/4.378917s alone is not that gate.
