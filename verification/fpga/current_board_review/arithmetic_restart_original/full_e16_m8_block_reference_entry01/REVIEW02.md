# Finite Reference Successor

NO_BLOCKER for exactly one full typed16 software reference via
full_e16_m8_block_unrolled01/reference_successor02.py, not DUT.
Entry02 SHA:b3c9bc0be15390aafba409adc471b890954f38cf767d14b511bf57c3e6ab8630.

REVIEW01 source/software findings carry forward. All156 pins freshly verified;
the complete prior150-pin set and blocked entry/driver are unchanged. No Host,
compile, reference or raw parse was repeated by this reviewer.

The sole blocker is resolved: finite `rs 4000000` invokes interactive_run,
which caps each chunk to the remaining steps and subtracts the chunk before
continuation. It does not rely on the debug-bypassed --instructions limit.
`quit` cannot turn a truncated reference into acceptance: the unchanged observer
still requires full4095/2096640/8190/4095vstart/53235helper/528255read coverage,
actual original console, software return0 and HTIF completion. Partial raw fails.

The successor removes the optional debugger minstret/mcycle receipt, explicitly
marks it unavailable and derives firmware count from the exact closed commit
ledger. This is not a fabricated counter measurement. Source, ELF, numerical
oracle, actual PC/code checks, little-endian16-bit data and lifecycle stay intact.
The actual tail instruction is LW at out+1024; high16 bits are guard005b, so
its value is nonnegative and the full4-byte expected value is appropriate.

Limits remain4M steps/120s/768MiB raw, one reference and one600s full audit.
Actual waits are saved before validation; all pins checked before/after.
Firmware<=3M may produce software READY; complete but above3M produces HOLD.
No automatic extension, rerun, DUT launch or Linux historical closure is granted.
