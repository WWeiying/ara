# Isolated Host Assertion Successor

Host01 actual1/474.249245s is preserved. Full5985 construction, strict oracle, generic delivery and owner finish completed;31 tests passed. The sole error was `test_actual_elf_abi` reading hardcoded0x800ffff8. The actual hashbound ELF has stack top0x800ffff0, frame272 and `sd ra,264(sp)` (0xe606), hence the correct address is0x800fffe8. Checker and Builder already agree on this address; neither is modified.

Four short tests now check the actual linked stack/frame/store-offset relation, saved RA0x80000052, wrong old address, BE/value and unknown-RA rejection. The original failed test/log/receipt and all consumed code pins remain bound. `host_composite.json` explicitly records old full Host rc1 plus new short ABI rc0, not an invented successful old process. No full Host stream, reference, compiler or DUT is repeated.

`prepare_successor.py` substitutes only this exact composite Host gate in a private copy of the existing prepare function. Runtime worker/checker, scope, budgets, numeric-first monitor and exit hook remain byte-identical. The final plan labels this composite admission and requires independent exact review.
