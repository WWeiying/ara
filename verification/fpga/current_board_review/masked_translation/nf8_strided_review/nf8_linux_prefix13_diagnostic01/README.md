# NF8 Linux Natural Prefix 13 Diagnostic

Latest deliverable: [fatal_successor01/README.md](fatal_successor01/README.md).
It preserves this initial build03 and fixes its fatal-record output limitation
with one bounded scalar write before the original exit2. The remainder of
this file documents the original build03, not the successor address map.

Status: **COMPILED_MODIFIED_LINUX_DIAGNOSTIC_NOT_RUN**. No board, Linux VCS,
reference, kernel build, or hardware acceptance was performed. No RTL changes.
No usable `qemu-riscv64` was found on PATH or in the existing
`/home/wangwy/openproject/qemu` tree; QEMU functional validation is NOT_RUN.
In particular, compatibility with the Linux vector signal frame is untested.

## Deliverable and Identity

- Runnable: `build03/nf8_linux_prefix13_diagnostic.elf`.
- SHA256: `c6af42f4b1fc5a992d7f60b3ac078fe3accb29f034f8645abbc6ee5f0b18698f`.
- Source, compiler commands, disassembly, symbol map and proof: `build03/`.
- Diagnostic additions: `diagnostic.h`; exact C edits: `build03/source.diff`.
- `ARTIFACTS.json` binds final artifacts and external original-source pins.

Original identity57 source is
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_fault_identity_regression57/source_mf2_False_0_nf8_stridedTrue_reverseFalse`.
The original manifest's shared C/generator hashes were checked; regenerating
the assembly reproduced the archived `.S` exactly. The original C+assembly
rebuilt with the existing non-ZCC Buildroot Linux compiler to byte-identical
ELF SHA `c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282`.

The diagnostic ELF is intentionally NOT byte-identical to the original.
All three assembly helpers match contiguous original machine-code sequences:
`capacity` (3 instructions), `replay_0` (44), `replay_1` (44).
The entire static RVV opcode sequence is unchanged, including the original
3-instruction compiler-generated sigaction structure copy in main.
Handler and added diagnostics contain no RVV instructions. The instrumented
scalar address map differs, so use this ELF's `diagnostic.dis`/`symbols.txt`.

## Exact Scope

Natural zero-based trials 0..12, with all 12 predecessors retained. Original
mmap/mprotect/munmap/sigaction, helper calls, fault repair, prefix poisoning,
mask generation, full-capacity output, full 8192-byte memory and guard oracles
remain. Stop occurs only after trial12's full oracle and munmap.
There is no alternate restart, fabricated warmup, or skipped check.

At original VLEN1024, SEW32/mf2 capacity is16 and VL is8: each trial checks
128 output words, both guards, and all 2048 mapped memory words. Last tuple:
`unmapped=0 store=0 boundary=1 mode=3 gap=1 split=0`, all-off mask, stride36,
target `mapping+4060`. This is not full192-case or historical-failure closure.

## How to Use Later (Not Executed Here)

Requires RV64 Linux with RVV and the original vector signal ABI. For the
historical comparison use VLEN1024 and retain kernel/image identity separately.
After separately authorized deployment, run the already compiled ELF:

```sh
./nf8_linux_prefix13_diagnostic.elf > nf8-prefix13.log 2>&1
rc=$?
printf 'process_rc=%s\n' "$rc"
```

Expected, not measured: 13 `NF8_LINUX_DIAG` rows followed by
`RVV_FAULT_REPLAY_PASS sew=32 cases=13 signals=12 errors=0`, process rc0.
An unexpected trial12 signal must be interpreted using its PC, frame and
first-check details, not assumed to come from the vector instruction.
Diagnostic target PCs: load `0x1109a`, store `0x11124`.

## Reading the Buffer Safely

Each preallocated scalar row records the first signal per trial and the first
oracle discrepancy. Addresses and `si_code` are printed in hexadecimal;
signed codes use two's-complement representation. With `signal_seen=0`, zero
signal fields are absent data, not measured CSR zeros. Likewise `check=0`
means no discrepancy recorded; `actual=expected=0` is then not a comparison.

The handler assumes valid kernel-supplied siginfo/ucontext pointers, as does
the original. This is not a validator for arbitrary/corrupted pointers.
It records their metadata but never dereferences the fault address or saved
PC. Vector metadata is read only after the original bounded header scan finds
a sufficiently sized vector record. No additional `datap` dereference occurs
before the unchanged frame checks. `frame_found` is not `frame_valid`.

Added diagnostic work is scalar buffer writes, not printf or write syscalls
inside the handler. Original repair syscalls and poison operations remain.
Printing occurs after all13 case oracles and cleanup, before process exit.
Original fatal/repeated-fault exit2 is preserved: it does not return to print
the buffer. Fatal text is saved as a pointer instead of printed in-handler;
debugger/core inspection would be needed if such an exit occurs. A core is
not automatically produced or promised. Buffer symbol is `diagnostics` at
`0x12058`; retain the symbolized ELF. No invalid-pointer recovery was added.

Phase numbers: setup1, protect2, helper3, return4, output5, memory6, guard7,
unmap8, complete9. `signal_phase` and `check_phase` retain event phase.
Check numbers: signal1, address2, code3, PC4, vstart5, VL6, vtype7,
saved-prefix8, prefix-memory9, returned-vstart10, signal-count11,
output12, memory13, guard14. `field/index` identify the checked coordinate;
memory index is a word offset from mapping, output index is within its field.
The original combined error counters are not split or inflated by logging.

## Preparation History

`build01` retains the compile error caused by the diagnostic field name
colliding with the system `si_addr` macro. `build02` compiled successfully,
but an overly strict static check rejected the original bootstrap RVV copy.
`build03` corrects the check to require equality with the original entire
RVV sequence; build02 and build03 are separate ELF artifacts. Neither
preparation issue is DUT evidence. No further compilation or run is needed
to consume this package. The fresh-build-only preparation script refuses
to overwrite build03.
