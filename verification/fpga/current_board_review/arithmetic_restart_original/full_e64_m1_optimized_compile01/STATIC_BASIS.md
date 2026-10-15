# Single O2 Experiment, No Source Reduction

The preserved -Os SoC disassembly has selected() at0x8000007a, including
remuw at0x8000008a for mode2. arithmetic_main calls it at0x80000398 (mask),
0x800004d4 (reduction),0x80000528 (compress),0x800005f0 (element oracle).
The last site spills a6/a5 at0x800005ec/0x800005ee and reloads them after call;
the full output loop also reloads operation-kind state from the stack.
Inlining and constant-divisor optimization at -O2 can remove scalar overhead.
This is a falsifiable compiler-cost hypothesis, not a hardware speed claim.

One successor experiment only: -Os becomes -O2 for both runtime ELF builds;
all other compiler flags, especially -fno-tree-vectorize and
-fno-tree-slp-vectorize, stay unchanged. Original C/runtime/assembly/helpers,
case/seed/RNG order, model and all result/guard checks must be byte-identical
to full_e64_m1_prepare01 source inputs. Host remains the same -O2 compilation.
All35 original13-instruction helpers and capacity must match archive bytes;
the reference whitelist rejects any extra vector instruction.

The prior -Os evidence remains immutable. One bounded Spike plus full raw
audit must verify5985/95760/11970 before any cost-based DUT admission. The
10800s DUT hard limit remains unchanged; no multiple-flag search is authorized.
