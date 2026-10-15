# Pre-Stream Host Adapter Cause

The constructed first-source probe exited1 at KeyError23 before starting the
full Host runner: the new mask unroll uses s7/t4/t6 loaded from physical_masks.
The old Host assumed all business store sources had arithmetic setter sites.
No DUT/reference/compiler ran. The new Host uses actual decoded non-stack LD
sites and values at the actual ELF physical_masks ROM; scalar ROM reads are
checked against those immutable bytes. No arbitrary missing GPR is defaulted.
