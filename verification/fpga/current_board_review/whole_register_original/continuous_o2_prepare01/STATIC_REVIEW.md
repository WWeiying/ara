# Sole O2 continuous1134 preparation

Static C review: no identified blocking UB/alias/volatile defect in this scope.
For op0..19/mode0..4 shifts stay within unsigned width; n<=8 and bytes<=16.
VLENB is bounded32..128; accepted starts <=evl and <8*VLENB. Arithmetic is
unsigned and bounded. Conditional input[i-32] is evaluated only when i>=32
and i<32+n*VLENB<=1056, keeping the index0..1023. Output loop covers0..1087.
Input/output are byte arrays with no type punning; external assembly functions
have writable output arguments and no pure/const annotations. No extra volatile
is needed for their memory effects. uintptr-to-long runtime convention remains
the existing RV64 LP64 port, not a claim of portable original Linux execution.

Frozen original prepare.py SHA9d68d255b61ae8658e6f6e378c7ca2ab05fefc50777bdadadcda9506fcdd61de
uses -Os for target firmware (-O2 was Host-only). Its compile logs contain only
stdout/stderr, not argv. New command receipts reconstruct that pinned recipe
and change only -Os to -O2 and independent paths; all C/.S/wrappers/runtime/linker
inputs are byte copies. WHOLE_OP_BEGIN=0/END=20; DETAIL_BYTES=1 remains.
Both -fno-tree-vectorize and -fno-tree-slp-vectorize remain; no LTO added.

Original actual SoC ELF hot loops at8000025a..270 and8000027a..290 execute
seven scalar instructions per initialization byte. The full1088 oracle at
800002d2..3a4 repeatedly regenerates addresses and branches on active bounds.
This supports one scalar optimization measurement, not a predicted speedup.
Original full reference33,497,309 instructions is below the fixed40M ceiling;
no static evidence requires exceeding that ceiling. Ceiling failure is terminal,
not grounds to increase it. Arithmetic O2's speedup is not transplanted here.

Both actual O2 compiles exit0; each backend's20 complete helper routines match
old machine encodings (all branch alternatives, not just one executed path).
No vector instruction exists outside original helpers. Tuple enumeration equals
the original ordered1134 calls and366 exclusions. BSS is below the unchanged
stack boundary, code fits2MiB. No partition binaries were compiled.
The initial postcompile nm-path typo and explicit non-recompile continuation
are preserved in PREP_ERRATA.md; no reference was attempted during that fix.

Reference design: normal non-debug Spike --instructions=40000000,120s hard wait,
RLIMIT_FSIZE4GiB. Local Spike sim.cc applies instruction_limit only in non-debug
idle, so no debug-until loophole. Success requires actual raw0 firmware exit,
HTIF1, exact console1134/366/0 and complete original input/result/status evidence,
not merely process0 at the instruction limit. One full streaming parser hashes
raw during its sole pass, checks all1,233,792 output bytes and1134 full1024-byte
input setups, exact helper branch paths/order and both vstart readbacks. Parser
hard wait600s. Actual numeric child exits are saved before acceptance checks.
No DUT launch and no automatic reference/parse retry.

Cost decision after reference: separate firmware through successful HTIF from
boot/parking. Use measured historical scalar/whole throughput proxies with
explicit margin; do not divide continuous workload by partition jobs. Even a
reference PASS is not launch admission or a measured <=3h DUT runtime. Preserve
the original source sequence and complete oracle if projected cost is too high.
