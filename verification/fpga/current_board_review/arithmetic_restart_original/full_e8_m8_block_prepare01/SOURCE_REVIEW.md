# Full E8/M8 Block Software Entry

Scope: one scalar-only software representation of the original CAP1024 full4095
sequence. No DUT authorization. Source/helper/Host/ELFs are frozen in pins.json.
reference_check.py/lifecycle.py/reference.py/test_entry.py and this note are
additionally frozen by entry.json. No original or prior artifact is modified.

## Original Identity And Equivalence

Original rvv_matrix_e8_m8 Linux ELF SHA
ee9874270f50735cb04da599bb477d3d9da2bbeba0e77cbec9e1eb1ea0f8310f;
original assembly e0dd3eb419e65813853869548fe54e278457005db90e032ed4a64ecb8aa5be08.
The C is the accepted binary-equivalent reconstruction, not recovered original
C bytes. proof.json binds exact original ELF/helper windows and each actual
SoC/Spike window. No claim of Linux replay or historical stall closure.

Three1024-element xorshift histories remain in original C and execute once per
seed; final RNG values are7396973484589540002,16389848989047954440,
11017945800333985713. Host verifies every a/b byte for every call, never reuses
cap512 fixtures. Original lengths0,1,2,3,512,1023,1024; all25ops and original
start/mode order including duplicates. All128 mask bytes are initialized and
verified. Original setup/helper old-vd/full-cap loads/stores are unchanged.

The new pure model's pool/index/full-output hashes match the independently
enumerated feasibility result for ALL4095 calls.3768 value-deduplicated64B
blocks,17 uint16 IDs per call,380766B including mask ROM. No calls are deduplicated.
Original physical a/b1024, out1026 and mask128 arrays remain. Per-call output
initialization/comparison touches exactly1026B, not1088 or1032. Last ROM padding
is zero representation only. No hash/checksum substitutes for byte comparisons.

Host original and packed each execute positive plus seven semantic negatives:
active, prestart, inactive, tail, leading guard, trailing guard and64-bit nonzero
returned-vstart. Every one completes4095 helper calls and4193280 result checks,
8190 guards, full physical masks; original and packed stdout/error count/return
are identical. The eighth negative is intentional shift64 and both UBSan
trap-mode binaries terminateSIGILL (-4). It is test-only, not candidate source.
Both variants also test every1026 output-byte flip and misaligned memcpy-safe
access. A protected Host page immediately after the exact1026B buffer rejects
any rounded-up read/write; the valid narrow-tail path passes.18 actual Host
receipts plus10 small Python lifecycle/model tests are retained, no repeated
reference execution. Host emulates helpers, not actual RVV hardware.

## C And Code Checks

Original integer source has no newly introduced signed overflow: e8 operands
promote within int range, shifts operate uint64 and mask amount by7; xorshift is
uint64. Signed conversion/right shift remains implementation-defined original
RISC-V GCC behavior, not a new algorithm. Pure expected block serialization uses
Python arbitrary-width integers; generated C constants are individually masked
uint64, so no C shift64. Fixed-size __builtin_memcpy gives alias-safe byte-pointer
access even with an unaligned Host test buffer. Main output base is aligned8;
out+1 remains the original unaligned vector destination pointer.

Compilation uses one -O2 configuration, -fno-tree-vectorize and
-fno-tree-slp-vectorize. Actual26 original routines match uniquely in stripped
Linux ELF; each op remains13 instructions and capacity3. Both ELF disassemblies
have zero vector instructions outside those original windows. Original slow C
result/guard fallback remains verbatim, including exact error count/diagnostics.
Returned-vstart check remains before the fast comparison. No pure/restrict,
runtime hint, source algorithm change or shortened prefix is introduced.

Spike actual code: initializer0x80000506..0x80000514 contains8 SDs, repeated16
times by +64/branch;0x80000524 SH covers only final2B. Fast comparison
0x80000560..0x800005c6 uses one LHU block ID, shift6/base add and8 LD/LD/branch
comparisons. Final0x800005d6 reads actual output with LHU;0x800005de reads the
expected low16 bits. It never loads8B from the last actual output fragment.
The reference lifecycle binds these exact PCs/instructions/order/address/value,
129 actual initializer stores per call, distinguishing startup BSS zeroing from
business initialization. No startup write can satisfy a missing per-call store.

Actual SoC ELF SHA60aca048666640ddab09f782d1435ea326a3875a8feadf36543d9df1a4edb68c,
stack gap658088B. Spike ELF SHA6e0e9cceaa2f59ae06aaa8ffe2112d5282b2b959edd3ed3f4a3a9a608b98cbc4,
stack gap649632B. Both pass the1MiB link layout's64KiB reserved-stack ASSERT.

## Sole Reference Gate

Tesla independent NO_BLOCKER must bind exact entry.json SHA before execute.
One invocation, `rs 4000000` (includes boot),120s host timeout and768MiB per-file
FSIZE. Cost admission target <=3M firmware, not a measured guarantee; a complete
reference above3M produces HOLD, never retries or increases a bound. The4M hard
ceiling accommodates the previously estimated2.8--3.6M range without silently
turning an incomplete3M trace into PASS. No until-PC unbounded debug command.

Numeric reference exit is persisted before postcheck. One offline fullraw parse
requires actual HTIF1, software return0, original exact console, full4095*13
helper PCs, physical8-register groups, all128 mask bytes, actual VL/VTYPE3/vstart,
fresh full1026B initialization,528255 packed reads/guards, returned-vstart zero
and input pins. Registers/CSRs are learned from actual trace, not initialized to
assumed zeros. Numeric audit exit is recorded separately. Missing completion,
trap, first failure, drift, wall/FSIZE/instruction cutoff remains NOT_ACCEPTED.
Reference numerical/profile acceptance does not authorize DUT.
