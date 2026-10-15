# Pre-Execution Cost Gate

The preparation searched current review READY/reference/complete/README records
for op4/ops4/merge_prefix/vmerge.vvm. No equivalent successful integer merge
prefix98 reference was found; existing FP merge195 and FP move ops4 are different
instructions. This is a bounded repository evidence search, not a global claim.

Host10 and software compilation have completed. Spike has NOT run when this
document and cost_table.json are created. No RTL build or VCS is authorized.

The reviewed executable is spike01/merge_prefix_e16_m8_ops4.elf, SHA
48a6cf76563eb0bbaf771858532237bd0a2c49d7edd3abf8021f1df1d8607e96.
Use the existing non-ZCC RISC-V GCC and original integer ISA profile
rv64gcv_zvl1024b. Integer SEW16 merge does not require Zfh/Zvfh.
Compiler flags/commands, tool hashes and both actual ELFs are retained.

The explicit compiled-loop table totals **4,309,396 instructions**, conservatively
charging the longest selected() and oracle path to every element, even prestart,
tail and VL0. It includes3584 original filtered iterations before op4,512 RNG
iterations,98*128 mask-clear bytes,98*512 predicate and result iterations,
98*514 output/guard initializations, all13 helper instructions98 times, loop
nest overhead and up to20 original failure diagnostics. No original empty
loop, input, predicate, helper or oracle is removed to fit the budget.

Addresses and per-iteration ceilings are in cost_table.json. They come from
the actual compiled ELF, not the earlier2.0..2.5M planning estimate. The bound
is a reviewed source/compiled-path bound, not a cycle prediction or formal
proof for arbitrary corrupted control flow. Unexpected traps/loops cannot PASS.

Reference ceiling: **5,000,000 debugger steps,120 seconds,768MiB per raw file**,
one invocation and no retry. The retired firmware bound leaves690604 steps
for bootstrap/endpoint slack. Log planning reserves160 bytes per scalar step
plus32768 bytes for every one of1274 helper lines (even non-vector ones):
731249792 bytes, below805306368. A512-element halfword store/read line and
eight1024-bit vector values fit that per-helper allowance. Actual tool/raw
limits are enforced; reaching a ceiling is not permission to expand it.

The accepted same-shape gather reference is about2M retired in3.3s with this
Spike binary;120s is ample measured host-throughput margin, not guaranteed
wall time. The upcoming sole execution must preserve its actual command and
raw logs regardless of result. This reference budget is unrelated to a DUT
timeout; no DUT admission follows from it.
