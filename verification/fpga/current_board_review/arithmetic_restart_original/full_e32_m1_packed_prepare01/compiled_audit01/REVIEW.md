# Host/Compile Complete, Static Cost HOLD

No Spike, DUT, RTL change, or live-job query. The previously reviewed three
static files remain unchanged. New software is in ../software01/.

## Actual Outcomes

Host/compile child PID3244669 returned numeric0, 17.476429774s, no timeout;
see ../software01/execution_receipt.json. Both original and packed harnesses
completed all5985 calls for each of12 runs: positive plus11 expected-negative
mutations. Original fallback diagnostics, errors and full-history counters
matched byte for byte across the two implementations. All binaries used UBSan
with trap-on-error; no sanitizer trap occurred in any valid case.

Two additional compiled Host variants each deleted one actual FP input store
at the second FP call, when the retained old value was identical. Both rejected
at call1367 with numeric90, after the exact input-value comparison passed and
before helper acceptance. Original source-block guards also reject deleting
either FP assignment or the next-seed RNG update (3 static negative checks).
These are Host source-instrumentation checks, not RVFI evidence.

Full positive Host scope:35 ops/5985 calls/191520 uint32 results/11970 guards,
5985 returned-vstart checks/1890 FP calls/120960 fresh FP word stores.
Tests include high-bit changes in both32bit guards, signed-zero sign change,
canonical-NaN payload mutation, FP low-bit mutation, prestart/mask/tail and
nonzero returned-vstart. Every one of136 output bytes was independently
mutated in the packed comparison test. Misaligned memcpy and a136B buffer
ending immediately before PROT_NONE passed without rounding up or alias casts.
The original1026-word output backing and unused a/b backing were preserved.

FP expectations are the original640 uint32 bit patterns: one unique identical
2560B sequence in the original Linux ELF and each compiled port ELF. No host
floating-point arithmetic generated the golden. Original per-FP-call source
loop, next-seed RNG, full fallback and original helper instructions are intact.
Signed casts/right shifts retain the original implementation-defined GCC
semantics; unsigned arithmetic, bounded shifts and guarded division introduce
no new UB. Only data/guards/vstart are the original result oracle; no fflags
result oracle is claimed. Initial fcsr0 is port setup, not Linux state replay.

## Actual Linked Artifacts

SoC ELF:82e0395a504f7583f5f1baa02426ca1f583947e93776c84e149ab8bb9e0d2e02.
Spike ELF:cd9a75ba80d9fffac14a6640d1b1e21527bfc915aafa5eb3a2ee8435016950fc.
Both retain capacity3 +35*13 =458 original helper instructions; extra RVV0.
SoC text5562/rodata818192/BSS12488, stack gap212264B.
Spike text5650/rodata818200/BSS20688, stack gap203808B.
Both exceed the64KiB reserve; main frame320B. The sums of all static negative
SP frame adjustments in C routines are496/544B, conservatively exceeding
any normal nested path here; no recursion or dynamic stack allocation.

Actual SoC FP stores:0x80000af8 and0x80000afc; Spike:0x80000af4/0x80000af8.
The15-instruction loop has32 iterations per FP call, two SW per iteration.
The op>24 gate precedes initialization/helper invocation and every trial's
backedge re-enters it; neither VL0 nor start>=VL bypasses this source loop.
Each ELF has exactly17 output SD and17 output LD sites at offsets0..128.
Actual compiled sites are recorded in RESULT.json; no universal PC relocation
delta was assumed between backends. Full execution counts remain predictions,
not measured retired events, until a separately admitted reference exists.

## CFG Cost Gate

inspect03.py read the actual linked Spike disassembly; actual tool exit0 is
recorded in actual_inspection_receipt.json. It counts disjoint mandatory
positive-path regions and bounds the remaining loop/control/boot/console paths.

| Mandatory region | Instructions |
| --- | ---: |
| Original128-byte mask clear,2205 groups | 846720 |
| Original32-position mask construction,3 modes | 676935 |
| Per-FP-call input setup and32*15 loop | 927990 |
| Call gate/setup/init/first compare | 263340 |
| Remaining16 compares and counters | 359100 |
| Original13-instruction helper calls | 77805 |
| Mandatory core total | 3151890 |

Even this mandatory core exceeds3M by151890, before remaining overhead.
The conservative successful-path upper is3320678, including bounded outer
control, BSS clearing and20000 instructions for final console/boot/exit work.
Failure fallback remains in the ELF and is tested; its execution cost is not
claimed to fit this successful-path bound. These are static CFG counts, NOT
Spike measurements or a reference PASS. Result is HOLD; no reference attempt.

The dominant removable scalar cost is the original byte-clear loop
(Spike0x800004d0..0x800004d6):128*3=384 instructions per mask group.
A possible separately authorized successor could replace ONLY this128-byte
zeroing with16 exact8-byte memcpy stores, retaining the32-position predicate
loop, every mask group, every FP input write and the full oracle. Store-only
saving would be(384-16)*2205=811440 instructions before changed setup/spills;
actual new code must establish the net bound. No such edit/compile is made
here; no table/history truncation, oracle removal, timeout increase or extra
vector instruction is proposed.

## Evidence And Limits

169 software/input pins were checked pre/post static inspection unchanged.
proof.json SHA e68e6df558fbf427940930750a5738a0c8e46ab88e26b222d78914f938b0431d.
RESULT.json SHA946b2d45dbd68ff59078091c17d2a80d3252ce5f5aaa49bc811b816ada1bc885.
Two earlier static-inspector parsing failures are preserved in
INSPECTION01_FAILURE.md and INSPECTION02_FAILURE.md with original scripts;
they did not rerun Host/compiler or invoke reference/DUT. Independent artifact
review is requested; source-port Host correctness is not architectural or
original Linux acceptance.
