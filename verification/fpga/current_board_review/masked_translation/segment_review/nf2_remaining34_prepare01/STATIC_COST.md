# Reference Bound Before Execution

Reuse the reviewed remaining4 source loop and its measured compiled-path cost
analysis, not repeated trial runs. The only C edits are the identifying comment
and PASS/FAIL marker. The header replaces its four literal configurations with
an included generated configuration and MX_N; assembly bytes are unchanged.
All groups have two complete memory/PTE checkpoints per case. The last group
has MX_N=2, not four slots with missing cases.

For N<=4, U unmapped cases, the conservative planning charges are:

- Full memory: 2*N*4096*45 instructions.
- Extra in-segment paths: 2*N*16*150.
- PTE validation: 2*N*512*45.
- Page initialization: N*4096*12.
- Page refill: U*2048*13.
- Vector/seed/output checks and initialization: N*1024*120.
- Fixed remaining CSR/handler/runtime/guard allowance: 200000.

Worst four-case group with all four unmapped: 2,672,704 instructions, below
the fixed 3,000,000 **per ELF** cap (stricter than 3M per case). The two-case
maximum is 1,436,352. This is a successful-path planning estimate, not proof
of termination under a defect. Each actual compile records its disassembly,
dimensions, exact configuration, charges, and code identity before admission.
Stop without execution if compile/dimensions/source constraints do not hold.

Each ELF gets at most one Spike invocation, 120s /3M steps /512MiB raw-file
ceiling, ISA rv64gcv_zfh_zvfh_zvl1024b, --priv=msu --pmpregions=0 -m2. These
reuse the accepted reference's envelope; no retry or expansion. Maximum three
reference processes. First reference failure or independent pilot failure
event stops NEW dispatch; in-flight bounded references retain their evidence.
No pilot polling, live simulation query, or DUT execution is performed.

The previous actual four-case reference had 1,315,037 parsed records, 23.18s
child+validation context, and 161,343,303 raw bytes. This supports feasibility,
but does not replace each new group's full oracle, HTIF success, or raw trace.

J2 exclusions are OLD M2 acceptance, not M6. The pilot4 exclusions are M6
inputs, with terminal acceptance pending independently. Preparing remaining34
does NOT prove current-M6 closure of40; that requires pilot4 terminal acceptance,
future remaining34 DUT results, and at most one unchanged old J4 ELF M6 replay
(two original failed singles plus two historical positive controls).
