# R168 Captured-Context Decoder

Run `python3 -B decode.py actual_context.json --out decoded.json`. Output is exclusive; no old file is replaced. Missing or contradictory register/stack evidence returns exit1 with `REJECTED_NO_TUPLE`. No register values are taken from the old counter snapshots. There is no real R168 dump in this directory.

Input schema:

```json
{
  "schema": "R168_REGS_STACK_V1",
  "source_elf_sha256": "a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b",
  "capture_id": "actual-capture-identity",
  "same_context_regs_stack": true,
  "regs": {"pc": "actual halted PC", "sp": "actual SP", "ra": "actual RA", "s4": "trial", "s7": "scalar pointer", "s8": "op", "s9": "length pointer", "a3": "VL", "a4": "capacity", "a6": "scalar", "a7": "start"},
  "stack": {"address": "actual SP", "byte_order": "little", "data_hex": "actual SP through SP+31 or more bytes"},
  "csrs": {"vlenb": "optional actual vlenb"}
}
```

Placeholders above are deliberately not runnable fabricated evidence. Integers or numeric strings are accepted; standard x-register aliases may replace ABI names. Exact original ELF/hash and caller/helper bytes are checked. At this leaf helper SP+0/8/16/24 are mode/seed/cap+1/completed count; ordinal is count+1 and all loop fields/arguments must cross-check. The decoder does not authenticate an externally supplied dump or prove backend acceptance/stall cause. Host fixtures explicitly identify themselves as synthetic and never close an archive record.
