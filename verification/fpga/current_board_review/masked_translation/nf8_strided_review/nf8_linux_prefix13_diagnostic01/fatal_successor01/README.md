# NF8 Prefix13 Fatal-Output Successor

**Compiled, static identity checked, formatter Host checked; Linux execution
NOT_RUN.** No board, VCS, QEMU, kernel build, or hardware PASS claimed.

Deliverable: `build01/nf8_linux_prefix13_diagnostic.elf`.
SHA256: `e7ce9267d6bdba32cdfe23af2f511bf50e7c0be662b19eebdf3a72438f283659`.
This is a modified diagnostic ELF, NOT the byte-identical original ELF.
`build01/proof.json`, compiler commands, `diagnostic.dis` and `symbols.txt`
carry the actual source/helper identity and address map. `ARTIFACTS.json`
binds these final inputs/outputs. No existing QEMU userspace signal ABI was
available for validation; no model or kernel was adjusted to obtain a pass.

## Preserved Scope

Same original identity57 e32/mf2/NF8 strided Linux program as ../build03,
natural trials0..12 with every predecessor, full output/memory/guard oracle,
original mask/init/repair/poison/syscalls and unchanged assembly. Stop after
trial12's oracle and munmap. Original rebuilt ELF remains byte-identical
`c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282`.
Helpers remain identical (capacity3, replay_0/replay_1 each44 instructions).
Entire original static RVV sequence is identical; no FP mnemonic found.
Original scalar-source changes from build03 are ONLY the fatal quit hook.

All original build03 proof pins remain unchanged. The successor owns its
header and preparation script; it does not modify the original header,
producer, source, logs, ELF, or proof. Earlier build failures remain evidence
of software preparation only.

## Fatal Behavior and Bounds

Normal handler behavior is unchanged: diagnostic buffer writes only, no
printf/write output added, and the original restore and poison operations.
After all13 ordinary cases, the normal diagnostic rows and original summary
print outside the handler. Only handler-originated nonzero quit additionally
serializes the current pre-recorded row as `NF8_LINUX_FATAL` before exit_group.
It does not return to the faulting instruction or repair again.

The fatal formatter uses a static1024-byte buffer, fixed keys and scalar
hexadecimal formatting, with no malloc, printf, FP, RVV, or longjmp. It does
not dereference context, datap, si_addr, PC, or the saved fatal-text pointer.
For a valid row the line is841bytes, including newline. One raw write to
stdout is attempted; short/error writes are NOT retried and exit2 is retained.
Output delivery cannot be guaranteed if stdout fails, is closed, or blocks;
the size/call count is bounded, not pipe latency. Configure a writable local
file for subsequent use. The original syscall/repair code is unchanged apart
from this explicitly authorized fatal diagnostic write.

The initial signal capture still relies on valid kernel-provided
siginfo/ucontext, as the original does. It is not an arbitrary pointer or
corrupted-kernel-frame validator. Vector metadata is copied after the
original bounded record scan and size check, before the original datap
validation; frame_found does not imply frame_valid. No extra datap reads
were introduced. Fatal output itself reads only scalar diagnostic storage.

Fatal values are all hexadecimal. `complete=0` marks an unfinished trial,
not oracle acceptance. `signals`/`handler_errors` are current counters;
signal fields retain the first signal even if the fatal reason is a repeat.
`signal_seen=0` or `frame_found=0` means corresponding fields are absent,
not measured zeros; `check=0` means no recorded oracle discrepancy.
An invalid trial index emits only exit/trial/counters without indexing a row.
Normal line fields and phase/check enumerations are documented in ../README.md.

Host-only `formatter_host.c` uses intentionally invalid *stored values* for
context/PC/address/fatal_message to verify they are not dereferenced during
serialization. Four cases passed: write return success/short/error and invalid
trial. This is neither an emulated signal handler nor Linux ABI validation.

## Later Authorized Use (Not Executed Here)

Requires original RV64 Linux RVV/vector signal ABI; use VLEN1024 for the
historical comparison and record the actual kernel/image identity separately.

```sh
./nf8_linux_prefix13_diagnostic.elf > nf8-prefix13.log 2>&1
rc=$?
printf 'process_rc=%s\n' "$rc"
```

Expected only, NOT observed: 13 complete diagnostic rows plus
`RVV_FAULT_REPLAY_PASS sew=32 cases=13 signals=12 errors=0` and rc0.
Trial12 is all-off: unmapped0/store0/boundary1/mode3/gap1/split0, stride36,
target=mapping+4060. Any signal there needs actual-PC attribution rather than
automatic attribution to NF8. Successor load PC=`0x113de`, store PC=`0x11468`,
diagnostic buffer=`0x12460`. Do not use build03's PCs for this ELF.
This13-case diagnostic cannot close full192 Linux scope or assert a HW fix.
