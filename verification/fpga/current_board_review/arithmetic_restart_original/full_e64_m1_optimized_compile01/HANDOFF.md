# Single O2 Successor: Full Reference Accepted

Original full_e64_m1_prepare01 remains untouched. Source/runtime/model are
byte-identical; the backend command differs only by owned output relocation
and -Os becoming -O2. Both autovector disabling flags remain. No matrix,
helper, RNG, seed order, guard, predecessor or oracle reduction occurred.

Static hypothesis confirmed: selected() calls and remuw disappear from the
optimized scalar oracle. The compiler outlines failure.part.0; the reference
checker recognizes the actual failure-entry symbol, with complete PC/code
whitelist and error-counter/oracle checks retained. Initial bound.json was
never executed; bound02.json pins that name adaptation before the sole Spike.

Full5985 calls,95760 results,11970 guards,5985 vstarts and77805 helper
instructions accepted. All35 original13-instruction helpers plus capacity
match archived ELF bytes; full source/global-RNG/FP transition order verified.
Host full positive and9 negatives passed; independent640-entry FP table match;
startup BSS1positive/11negative tests passed.

Actual Spike exit0:8.488814124s,306705632 raw bytes. Actual full raw audit
exit0:68.811921906s,PID1948943,attempt1. No reference retries.
Firmware through HTIF:4528858, versus5908244 for -Os (1379386 fewer,23.35%).
Measured-M6 projections with20% margin:9199.936261s from e32mf2 and9146.192902s
from e16mf4, below unchanged10800s. These are estimates, not runtime guarantees.

READY SHA256: fb00c9c6aee09d5de5fe7fab159151a6a278f8ac4cd113dbe5950389b8ea444f
SoC ELF SHA256: 19dfd4e46b871e53cce075263cc96a1ab77e28ea7b2ac20ecd0762830cf2b4ea
Original Linux ELF SHA256: 5c15d5227aacb7ccd7115f7f2379081f21d33c928358055caebe4dd480ceebe2

The optimized software is an exact-source/runtime derivative, not original
Linux binary identity. The original C text remains a byte-equivalent recovered
reconstruction. No explicit fflags oracle exists in the original and none is
invented. Run preparation: ../full_e64_m1_o2_vcs_m7_plan01. New frozen M7 only;
no RTL or image build and none of the17 larger shapes is touched.
