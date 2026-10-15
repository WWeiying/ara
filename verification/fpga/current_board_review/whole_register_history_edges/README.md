# Whole-Register Missing History Edges

Preparation only, independent directory. Do not launch DUT, alter sealed
whole_register_original inputs, or query ongoing NF7/NF8 jobs from this task.

`prepare.py` reads the original prepared01 source/provenance and reproduces the
exact original1134 executed tuples and366 exclusions. It computes the original
adjacent-call set minus the adjacency retained in the20 operation partitions.
All59 missing pairs, not a representative subset, are selected in original
order. Each pair is an independently compiled executable and fresh Spike
runtime: two original calls plus their intervening original exclusions.

The sole oracle-port change is a candidate-ordinal range guard inside the
original loop. Original input setup, output initialization, skip predicate,
function call, status/vstart readback checks and entire1088-byte output oracle
remain byte-identical. No reset or warmup is inserted between the two calls.
The exact original assembly is copied unchanged. Unselected candidates still
traverse scalar loop control, but do not initialize vectors, call operations,
or count as original exclusions. The extra scalar selection changes timing;
this is not instruction-for-instruction original continuous history.

Each host pair checks the unmodified original oracle and seven corruptions:
prefix guard, first body byte, last body byte, immediate suffix, final guard,
nonzero returned vstart, and wrong captured initial vstart. Coverage negatives
reject missing/duplicate/reordered pairs and changed tuple geometry.

Both Spike and SoC ELFs use the sealed original integration runtime. Spike
commit logs independently check two exact target-PC/opcode retirements, four
original whole preloads, two output whole stores, both complete input/output
initializations, both ordered1088-byte scalar output scans, call arguments,
raw exit0, trap-free execution and exact original completion markers.
Debugger reads capture vtype before each original operation's preloads and
verify the second call inherits its predecessor's vtype; minstret and full
trace retirement counts provide actual reference instruction measurements.
SoC compilation is preparation only, not simulation.

```
python3 -B prepare.py --out prepared01
```

Per-process compile60s, host10s and Spike90s bounds; stop on first failure,
preserve evidence, and do not silently retry. All files and logs are new owned
outputs. `input_pins.json`, `selection.diff`, `edges.json`, per-pair metadata
and final complete.json are the provenance/review entry points.

Passing all59 references or a later DUT supplement would cover only local
predecessor effects under fresh-start context. The first call lacks its earlier
original history. It is not continuous1134-history acceptance, original Linux
ELF/OS replay, or a waiver of the original exclusions.
