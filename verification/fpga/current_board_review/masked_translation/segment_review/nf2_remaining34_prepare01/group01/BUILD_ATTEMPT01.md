# Preserved Software Build Diagnostic

`reference01` contains the first successful SoC software compile/disassembly,
followed by a builder identity-check error: `KeyError: mx_guard_lo`.
The assembly `.globl` labels have no ELF `.size` directive, so `nm -S` does not
report their sizes. This is not a compiler, reference, or DUT failure.

No Spike invocation occurred. Successor output uses `reference02` and checks
the actual labels `guard_lo+64 == pages` and `guard_hi == pages+20480`, with
the original unchanged assembly `.zero 64` declarations. C array dimensions
still require their actual ELF symbol sizes. Original output is retained.
