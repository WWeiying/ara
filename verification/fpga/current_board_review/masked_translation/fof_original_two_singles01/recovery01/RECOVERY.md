# Startup Completion Classification

The unique e8 reference process exited0 in2.974492575s; raw20376118 bytes,
no timeout. Its original `reference_e8_01/not_completed.json` is retained as
NOT_ACCEPTED. This is not a DUT failure or an accepted reference result.

Bounded first-write inspection found raw line24721:

```
core   0: 3 0x0000000080000046 (0x0002b023) mem 0x0000000080007060 0x0000000000000000
```

`fx_completed=0x80007060`; this is startup's aligned `sd zero,0(t0)` BSS clear,
not the final DONE publication. The original checker incorrectly required DONE
and restored CSRs on this initialization write before main.

The new observer differs only in its owned utility path and completion-write
classification: before main it requires exact `_start+0x46`/0002b023, width8,
zero value and full aligned object inside BSS; after main it still requires
width8/DONE and the complete original saved/restored CSR checks. No source,
ELF, oracle value, count, bound, first error, raw or approved input is changed.

The e8 successor is an offline check of the same unique raw, not a Spike retry.
The e64 reference has not been dispatched yet; its one allowed run uses the same
previously built/pinned ELF, limits and new observer. Both success gates retain
full original11/capacity3, true S-mode, precise read addresses, physical data and
oracle/CSR/HTIF checks. All corrections and Host results are new owned artifacts.
