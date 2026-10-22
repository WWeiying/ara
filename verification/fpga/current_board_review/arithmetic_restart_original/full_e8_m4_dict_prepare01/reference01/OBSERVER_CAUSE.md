# First Reference Observer Rejection

The sole actual Spike child returned 0 in 10.546864655334502 seconds, without
timeout or retry. `execution.json` deliberately remains `validated:false`.
The original full4095 console marker reports all 2096640 elements and zero
errors. The actual debugger minstret is 0x28627e (2646654), below the three
million instruction admission target. These receipts alone are not full raw
oracle acceptance, nor DUT acceptance.

The first observer rejection is `Output setup writes beyond exact514`.
The first matching actual commit is line356:

```
core   0: 3 0x0000000080000046 (0x0002b023) mem 0x0000000080097b18 0x0000000000000000
```

PC80000046 is the frozen runtime startup's `sd zero,0(t0)` inside the full-BSS
zeroing loop, before entering main. `out` is80097918; this address is out+512.
The eight-byte startup write legitimately spans the final two checked bytes
and six additional bytes inside the original 1026-byte static output array.
It is not a per-call initialization write. The per-call compiled source uses
64 scalar LD comparisons and an exact LHU at out+512, and its initialization
ends with the exact two-byte tail. Host whole-array footprint checks passed.

The new observer tracked every scalar store overlapping out, including the
bootstrap, as a per-call setup write. That conflates two different lifecycle
owners. A narrow offline successor should maintain bootstrap memory state,
but only count and bound stores owned by the actual `arithmetic_main` function
as per-call fresh514 initialization. Every-call coverage, expected initialized
values, all physical vector output bytes, all65 oracle reads and original13
helper ordering must remain unchanged. Do not exempt arbitrary business stores
or widen the 514-byte per-call contract.

Original raw log, numeric receipt, executor and STOPPED remain intact. No second
Spike execution, DUT run or source/RTL change is needed to investigate this
observer-only boundary. Full raw acceptance is unresolved pending that offline
successor review; this file does not claim READY.
