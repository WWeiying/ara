# Full682 Scalar Optimization Preparation

Budget-feasible preparation, NOT DUT admission or DUT PASS. Original682
artifacts, original17920-call parent and accepted first50 remain untouched.
This successor retains all682 original calls/681 predecessors, not a shorter
prefix and not Linux ABI equivalence. No RTL/image build/DUT was launched.

## Basis And Measurement

Original -Os input/oracle loops dominate20,260,288 reference retirements.
One -O2-only experiment, autovectorization still disabled, preserved original
C/runtime/assembly and returned0 with all682/errors0,17,793,250 retirements.
This is still over budget. No search across compiler flags was performed.
Initial objdump path construction failed after successful SoC compilation;
measure02 resumed without recompiling SoC. One compilation per backend and
one actual Spike cost run for that candidate. Earlier failed records retained.

Packed successor: one SoC compilation, one Spike compilation, one Spike cost
run (PID2029062,actual numeric exit0,0.417914194s),2,123,849 retirements.
Full682 PASS/errors0 observed. This is a debugger cost measurement, not a
new full raw/dynamic reference audit. Runtime counts stop at replay_exit,
consistent with the old budget baseline; they are not RTL cycle counts.

Projection using measured M7 e64-O2 full-run throughput:
3537.575s nominal /4245.090s with20% margin, below10800s.
Same e16/m8 alias first50 M6 accepted throughput gives2667.212/3200.654s.
Different scalar/vector mix and concurrency can change throughput; neither
projection is a guarantee. Do not extend the3h DUT limit automatically.

## Exact Preservation

The original nested loop order,682 after-oracle stop, capacity call, function
dispatch, full128 mask initialization,130 output-byte initialization, helper
arguments, returned-vstart/flags comparisons and both guards remain.
All512 a and b halfwords are still written before every helper; the unused
upper halves of the original1024-entry arrays remain BSS zero as before.
Only their scalar construction is replaced by128 aligned64-bit copies each.
Five deduplicated input rows encode the exact deterministic original inputs.

For every result bit, two packed masks represent must-zero and must-one.
For active bits the fixture determines one value; VL0 preserves alias bits;
tail bits retain the original allowed set {old,1,wanted}. No observed Spike
value is used as a golden. All64 result bytes (512 bits) are examined. Packed
error counting is per failing byte rather than per bit; PASS/failure semantics
are identical, but detailed error totals on multi-bit corruption may differ.
Flags are the original sticky bit OR all active fixture flags.

Host independently evaluates11,173,888 byte alternatives (every0..255 value
at every byte of every call),698368 input halfwords and682 flags outcomes.
Additional binaries execute actual original C and transformed C: all682-call
records are byte-identical for parameters/order,a/b,mask,and130-byte initial
output. One positive pair and six negative pairs passed: VL0 alias bit,
active result bit,leading/trailing guards,flags,returned-vstart. These are
scalar Host proofs, not dynamic RISC-V ABI/VRF claims.

Original Linux ELF SHA266467e6... equals retained original_rebuilt.elf.
It is stripped: complete capacity(3 instructions),op0..3(16 each),op4..9(21
each) sequences each occur exactly once and byte-match the new SoC ELF.
Helpers also byte-match previous SoC/Spike images. Static instruction scan
rejects new vector instructions outside helpers; no scalar FP arithmetic was
added outside helpers. Same helper calls/data and no interposed vector code
preserve the intended VRF history by construction; dynamic confirmation and
the relocated-PC checker remain admission work.

## Memory

Input ROM5120 bytes;682 parameter/oracle records98208 bytes. No1.4MiB ROM.
SoC __bss_end=0x8001b330; Spike __bss_end=0x8001d438.
Original linker LENGTH=1MiB and __stack_top=0x800ffff0 unchanged, with the
existing64KiB reserved stack assertion passing. Hardware2MiB remains unchanged.
Thus no data/stack collision or stack relocation is required.

## Handoff

READY.json binds source/Host/provenance/cost evidence through pins.json.
SoC ELF: run01/soc.elf, SHA
9a541b0d10d243b02b14136accb65bb9e9d3dcc4b18716c96239e719adaa5044.
Spike ELF SHA061f1daf04e14edd855fa8ec5900b56d892582ea047e35ee30ab25f96200454a.
Remaining before launch: independent transformation review and a worker/Host
binding exact new PCs, packed checks, full input/helper/order/flags/guards,
real numeric exit and frozen M8 identity. Old per-bit checker must not simply
be disabled or reused under incorrect scalar-PC/read-count assumptions.
No worker/runplan prepared and no M8 launch claimed by this preparation.
