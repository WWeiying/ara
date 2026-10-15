# NF8 Remaining Scope Review

Date: 2026-10-12. Read-only evidence/source review; only this new report written.
No CSV reparse, helper execution, build, simulation, live query or RTL change.

## Conclusion

Do not repeat selected4 or the full192 Sv39 campaign to close the historical
169-versus128 issue. All192 source-derived tuple/layout/data-oracle scenarios
already have independently accepted M4 DUT results. CURRENT_SCOPE.md's older
statement that full192 is not covered is stale relative to the terminal audit.
This is not a new M6 result or unconditional original-Linux-program acceptance.

The one actionable remaining gap is attribution of an unexpected SIGSEGV in
the original Linux all-off path, including its actual PC and saved vector
context. The first such original tuple can be bounded to trial12 with its
12 predecessors retained. The extra41 errors remain unlocalized; this report
does not claim that finding the signal discrepancy explains those41 errors.

## Original Evidence And A Narrower Inference

Original ELF SHA256:
`c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282`.
Recovery12: cases192/signals192/errors169/exit1. Recovery13 previous_report is
the same observation, not another run. Same-ELF retest:192/192/128/exit1.
Archived VLEN512 and1024 references:192/144/0/exit0.

In identity57-bound `fault_replay_oracle.c`, line120 exits2 immediately on a
second handler entry in one case; line243 resets faults for each case;
line258 accumulates faults, and line275 completes the case. Therefore, under
the source's counter semantics, completing192 cases with192 signals implies
one handler entry in every case, including all48 mask-zero cases. This is a
source-derived inference, not a recovered per-case trace. Memory corruption
of these counters is not independently excluded by the historical summary.
The signal could be at an unexpected scalar/helper PC; do not label it a
target-instruction page fault without capturing the PC.

`errors` includes combined trap metadata, saved prefix, returned status/fault
count, final registers, memory and guards (lines151-163,257-274). Neither169
nor128 counts numerical failures or distinct failing tuples. Aggregate41
cannot identify a field, phase, or root cause.

## Already Covered And Smallest Material Differences

The accepted48 four-case ELFs cover original trials0..191: unmapped0/1,
store0/1, boundary1/3/5, masksff/aa/24/00, gaps1/3, split0/1. Original assembly
is retained; VL8/e32/mf2/tu/mu, fields v24..v31, strides36/44 and
base=M+4096-boundary*stride-16*split match. At VLEN1024 cap=16 words/field.
Input101+13*i+29*f, oldvd0x5b, full128 output words plus guards, original8192
memory bytes/gaps, prefix checking/poison and unchanged-PC/vstart restart
are covered; physical fractional tails and neighboring registers are stronger
additional checks, not a narrower substitute for the original data oracle.

The independent terminal audit actually reread all48 CSVs:594288 comparisons,
11193408 checkpoint bytes,144 page faults,48 all-off no-fault cases, zero
errors and zero CTRL exits. It verified726 pins and M4 image membership.
Historical systemd exit was not recoverable after collection; retain that
separate qualification rather than treating missing-unit defaults as success.

What differs: the fixture executes S-mode under an M-mode trap handler, using
fixed VA0x40000000 and direct PTE repair/SFENCE. ACCERR uses execute-only data
PTE with MXR0, MAPERR an invalid leaf. The original uses Linux mmap/mprotect
PROT_NONE/munmap, SIGSEGV siginfo and kernel signal-frame save/rt_sigreturn.
The fixture reads architectural CSRs/register snapshots instead of validating
Linux sc_extdesc/datap/si_code. Four-case fresh ELFs also omit the original
continuous192 Linux process history. Same opcode and relative layout do not
make these runtime/context paths equivalent.

## One Proposed Next Reproducer (Not Prepared Or Authorized Here)

Use an owned source-derived diagnostic of the original Linux prefix0..12,
not another Sv39 port. Preserve all original setup, assembly, mappings,
signal action, repair, poison, oracle and predecessor calls. End after13
completed cases. Trial12=(unmapped0,store0,boundary1,mode3,gap1,split0):
VL8, mask00, stride36, base=M+4060; no target fault is allowed. Expected
prefix aggregate is cases13/signals12/errors0. Its source-derived counterpart
is already covered in full192 group03; the missing evidence is Linux execution.

Add only bounded diagnostic recording: exact tuple including gap/split,
phase/check ID, actual signal PC/si_code/si_addr, saved vl/vtype/vstart/vlenb,
and first got/want with field/index. Record into preallocated scalar storage
and emit outside the handler; retain sticky first failure and all original
checks. Existing TRACE_REPLAY lacks gap/split and per-error got/want, so merely
enabling that flag is insufficient. A changed diagnostic ELF must be declared
as such, with source delta and target assembly identity pinned, not advertised
as execution of the byte-identical original ELF.

Before any future run, bind the archived failing board/kernel/runtime image
identity or explicitly record that it cannot be recovered. A current-image
PASS would close this bounded current Linux path, not retrospectively explain
169/128. If no matching Linux environment is available, leave this gap open;
do not substitute another already-covered bare-metal full192 run. No runtime
budget is inferred from the archived20-second whole-program observations.

## Evidence Identity Rechecked Now

All15 non-RTL selection provenance pins match, including original/archive/
identity57 ELFs, C/generator, reports and references. Current fixture.c/h,
reference.py and selection ledger match the frozen full192 plan pins.
No raw CSV or full simulator image was rehashed in this bounded review.

- `selection01.json`: `d22f9dc7f2817c27bffdf006317d964605f4a8c99bb53588fa646fc1271a1c9c`.
- `sv39_full192/terminal_resume20261011.md`: `a15e3594d191d8cc27abc8f961e357004ed1a6d77b4e6d74a9b70f6a79ea2ada`.
- `sv39_full192/vcs_jobs8_plan02/plan.json`: `28785e754a948e29381f3c68faa1cbb3c0f393d7bb195d0b192b973606aa56b4`.
- Its `complete.json`: `e022b6d21aa827276d7ed6af6cdd9d4226aae1e65645ae3b64d72b4796f50fb9`.
- `sv39_full192/fixture.c`: `3e4a5b7e11e16c36ac91a8376fe48cc1d0536cf15b5ebf67a9602c7e25e923d2`.
- `sv39_full192/reference.py`: `bdc2f7d906342f88d258a2b5f42d8e4dcbaa282bd96740f4cf853fde71ee108e`.

CURRENT_SCOPE and all existing reports/inputs remain unchanged.
