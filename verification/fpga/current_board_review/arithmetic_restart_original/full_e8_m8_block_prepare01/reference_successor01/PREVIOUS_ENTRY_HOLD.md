# Previous Entry Held Before Reference

Tesla independently found a deterministic observer bug before any Spike run:
old reference_check.py's nested group() requires eight physical vector registers
but concatenates only four. CAP1024 comparisons would necessarily reject512B.
Old entry SHA b4d39e48be697aa3d02d95bab31d42fb57ae0aa1df14be8019e1074595b67125
and all130 pins are preserved; this is not a DUT/reference execution failure.

Only the reference observer/driver binding receives a fresh successor. Both
compiled ELFs, original C, expected tables, Host equivalence and source/helper
proofs remain byte-identical. The corrected group concatenates all eight physical
registers; a test extracts the actual nested function from its AST, exercises
distinct high-half bytes, and rejects missing high registers. No comparison or
oracle is weakened. No automatic old-reference retry exists: no first reference
has yet been executed.
