# Linked Positive CFG Method

This is static successful-path accounting of the two already linked binaries,
not Spike, an architectural reference, or DUT execution. The original Host
numerical acceptance supplies the successful helper-output hypothesis. Both
backends are walked to their actual finite completion store. The park loop is
not firmware work; no successful runtime code polls a device or waits for input.

Pre-execution inspection found only the scalar opcode set explicitly supported
in `linked_cfg_audit01.py`. The source helpers are straight-line: capacity has
3 instructions; each of four operations has 24, including all 9 CSR operations
(4 rounding/saturation save/restore instructions). All are charged at actual
PCs. Their full 99-instruction concatenation must occur uniquely in an executable
segment of the stripped original ELF and match both new linked binaries. There
is no default-zero treatment of unknown scalar values, branches, or opcodes.

The walk follows actual scalar branch constants and original tuple arguments.
All 10752 helper calls, 4416 source byte assignments, 336 mask epochs with 16
clear stores followed by the original cumulative selected-byte writes, and
every per-call 64 SD plus SH / 64 LD plus LHU sequence are checked. The linked
immutable tables are byte-matched to the independently Host-validated model.
Only the hypothetical vector writeback deposits expected result bytes; it does
not touch either guard, input, mask, stack, or scalar counters. Argument and PC
ledgers retain the source order. Scalar caller code, branches, spill/fill, RNG,
printing, BSS initialization, startup, and finite exit are counted, not assigned
a guessed overhead. All 28 original boundary messages and final counters must
be reached. Errors and fallback functions are forbidden on this positive path;
their original semantics were independently tested in the Host stage.

Unknown entry callee-saved GPRs are opaque and can only be spilled/restored on
the bounded stack. Fixed capacity512/VLENB128 and successful vector outcomes
are explicit assumptions, not observed CSR or hardware states. CSR save/restore
code identity is established, not final-state physical readback.

The runner permits one child with a 600-second wall limit, writes the actual
numeric wait result, preserves first failure, and never retries. Each complete
walk also has a 12M-instruction diagnostic ceiling; crossing the 3M cost gate
does NOT stop counting. An auditor defect is not a firmware-cost result. A
complete Spike-backend linked positive count above 3M results in HOLD, without
reference, target recompilation, or another optimization attempt.
