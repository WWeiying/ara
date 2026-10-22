# Full E8/M8 Reference Entry

Decision for entry `b4d39e48be697aa3d02d95bab31d42fb57ae0aa1df14be8019e1074595b67125`:
**BLOCKED_CHECKER_BEFORE_REFERENCE**. No reference or DUT was executed by this reviewer.

## One Concrete Blocker

`full_e8_m8_block_prepare01/reference_check.py`, nested `group(first)`,
requires all eight physical registers but returns only `range(first, first+4)`.
The resulting512 bytes cannot equal the actual1024-byte inputs/old-vd required
at the first target. This is an inherited m4 observer width, not an RTL fault,
source-oracle discrepancy, or failed reference execution.

Aquinas acknowledged before any Spike invocation. Preserve the old entry and
implement a narrow owned successor joining eight registers with actual group
positive/high-half corruption/missing-high-register Host checks. Do not relax
the1024-byte comparison, alter ELF, or repeat the complete equivalence Host.

## Other Entry Checks

- Independently hashed all130 pinned inputs: unchanged.
- Read actual SoC and Spike ELF load segments and helper bytes, not merely
  disassembly labels. Each has26 original routines/328 static instructions;
  each original window matches uniquely in the archived Linux ELF.
- SoC SHA `60aca048666640ddab09f782d1435ea326a3875a8feadf36543d9df1a4edb68c`;
  Spike SHA `6e0e9cceaa2f59ae06aaa8ffe2112d5282b2b959edd3ed3f4a3a9a608b98cbc4`.
  All load segments fit the1MiB region; stack gaps658088/649632 bytes exceed64KiB.
- Source diff retains original three CAP1024 RNG histories,25-op/full4095
  sequence, original helpers and slow diagnostic fallback. Mask initialization
  covers128 bytes, not an m4 upper-half-zero assumption.
- The packed path compares16 blocks of eight64-bit words and only two bytes
  of the17th block. Fresh initialization is128 SDs plus one SH, exact1026 bytes.
  Fixed-size memcpy avoids unaligned/aliasing UB; out+1 remains the original
  vector destination. ROM380766 bytes is below the image/stack bound.
- Actual original and packed Host receipts each show0, seven1 outcomes and
  intentional UBSan trap-4. The10 existing lifecycle/model tests exited0;
  they did not exercise the faulty physical-group concatenation.
- Lifecycle uses exact startup BSS PC/order/bounds before main, and separately
  requires129 actual initializer stores for every helper entry. BSS cannot
  substitute for missing per-call initialization or legalize a wide final store.

## Bounded Reference Contract

Both executor and observer use4000000 instructions including boot, not an old
6M limit. Executor host limit120s, per-file raw limit768MiB, one attempt with
durable numeric exit before postcheck. Full acceptance requires4095 calls,
53235 dynamic helper instructions,4193280 results,8190 guards,4095 vstart
returns,528255 packed reads and actual HTIF1/software return0. The separate
<=3M firmware cost target is not the hard execution limit: a complete pass
above3M must remain HOLD. A hard cutoff must never become partial acceptance.

No other concrete blocker was found in this narrow review. The corrected
successor must bind the unchanged software inputs and its own actual Host and
entry hashes before the single already-authorized reference is dispatched.
