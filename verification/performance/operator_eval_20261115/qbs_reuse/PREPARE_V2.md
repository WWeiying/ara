# Prepare V2

Use `prepare_v2.py` with the same arguments documented in README.md.
The original `all_01` preparation failed its disassembly-inspection gate because
GCC emitted `validate.constprop.0`, not the literal `validate` symbol. The host
full-comparator mutation test and six real-data SDK/context calls already passed.
The original directory, inputs, logs and source files remain unchanged.

V2 resolves exactly one actual validation function in the ELF symbol table, then
requires its disassembly to call all three complete comparison functions. This
does not change the firmware, numeric contract, input data, timings, tests, or
any sealed original QBS source. No failed build is relabeled PASS.
