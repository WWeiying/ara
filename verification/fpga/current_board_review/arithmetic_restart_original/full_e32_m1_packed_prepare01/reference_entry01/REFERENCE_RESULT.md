# Full e32/m1 Reference Result

Status: REFERENCE_FULL5985_PASS_SOFTWARE_ONLY_NOT_DUT.

The single authorized reference and single closed-raw audit completed without
retry. No DUT, RTL change, repeated Hostcompile, or second reference was run.
Software01 HOLD and all prior sealed inputs remain unchanged.

## Admission and Actual Outcomes

- Entry SHA256: `011a92d114214be61a6c376f352e140cb7e6cf76895fb5421165b452642b61a2`.
- Averroes final review: `e32_m1_packed_source_review01/reference_entry_result.json`
  relative to the arithmetic review root; SHA256
  `d117c3552611543047b4e2ab090b689ce58ad3043f2956d832d88984d75f4ab9`.
- New observer Host: 21 tests, actual exit 0, outer 31.396274 seconds.
  Its constructed full-history bridge is not ISA execution evidence.
- Actual invocation: `python3 -B reference.py execute --review <absolute final review path> --review-sha d117c3552611543047b4e2ab090b689ce58ad3043f2956d832d88984d75f4ab9`.
  Runner tool session 5941 completed with actual exit 0, output
  `READY 2472244` (completion receipt chunk `19fd00`).
- Spike PID 3272454: numeric exit 0, 5.293743 seconds, timeout false, retries 0.
- Closed audit PID 3272492: numeric exit 0, 76.163390 seconds, timeout false,
  retries 0. One complete raw parse, not metadata-only acceptance.
- Fixed bounds: debug command `rs 4000000` then `quit`, Spike 120 seconds,
  raw 768 MiB; audit 600 seconds. Exact ISA `rv64gcv_zvl1024b`.
- Firmware through actual HTIF success: 2,472,244 instructions, below 3,000,000
  by 527,756. Observed whole raw: 2,475,000 rows, including 5 boot rows and
  2,751 exact side-effect-free post-HTIF park rows; EOF checked.

## Complete Accepted Scope

- Original 35-op, three-seed history: 5,985 calls, 191,520 uint32 results,
  11,970 uint32 guards, and 5,985 returned-zero vstart values.
- All 13 original helper positions execute 5,985 times each: 77,805 helper
  instructions. Capacity bootstrap counts are exactly `[1,1,1]`.
- Per-call exact output is 136 bytes, read as 17 full 8-byte words:
  101,745 reads. There is no fictitious short tail read.
- Every one of 1,890 FP calls has 64 fresh scalar input writes, including
  unchanged-value writes: 120,960 total. Three integer seeds have 276 original
  initialization writes. Original 640-entry FP bit-pattern table is retained;
  this does not claim that all 640 input/result combinations are executed.
- All 2,205 mask groups retain 35,280 exact zeroing stores and 38,955 original
  selected-bit stores. Physical mask is 128 bytes; actual vlm reads 4 bytes.
- Full physical register is 128 bytes, one register per group. Original
  helper bytes, RNG/history, oracle, fallback, actual scalar sites, and source
  pins were checked. All pre/post pins remained unchanged.
- Original console: `RVV_MATRIX_PASS sew=32 vlmax=32 cases=5985 elements=191520 errors=0 seeds=3 guard_tail_mask_vstart=checked`.
- Startup fcsr-zero instruction is checked. The original test has no fflags
  result oracle; this acceptance does not claim exception-flag coverage.

## Evidence

- `READY.json` SHA256: `d1f70125ab071283390749323120204356e07da6a3a420f450e46c58e5859691`.
- `reference01/result.json` SHA256: `60bcfb49961f43021851fc2ea58b08269129ea4d457db7162c046e9953e9984c`.
- `reference01/execution.json` SHA256: `e6308125d508052e31657f9141ab3866818e68eb0a3bafad47a62f8799d785fa`.
- `reference01/audit_execution.json` SHA256: `7a72d7ccf384d9b522c821b267462642744d8d707a04860bc0da1c7a33e433b2`.
- Closed raw: 197,069,053 bytes; SHA256
  `8b8da8e8cc21eea3a4579abaf14a8a3fe004b8044fe064ce3ca8a2364d376e40`.
- Exact commands, independent review binding, and pre/post pins are recorded in
  `reference01/command.json`, `audit_command.json`, and `preflight_pins.json`.

The retained projection is 7,343.84 seconds with its stated 20-percent margin,
not a measured DUT runtime or guarantee. This is a source-derived bare-metal
software reference, not Linux replay or current RTL acceptance. No DUT launch
is authorized by this report.
