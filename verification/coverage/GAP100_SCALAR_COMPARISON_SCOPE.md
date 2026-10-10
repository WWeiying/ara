# GAP100 Scalar Comparison Scope

This is software-preflight scope, not DUT acceptance or a coverage receipt.
Baseline: exact historical708; RVH=0, PMP entries=0, no external IRQ source.

## Deterministic Phases

Twelve HPM3 probes independently initialize mcounteren/scounteren bit3. The
counter is zero with event selector zero. Expected permissions are M: allowed;
S: mcounteren[3]; U: mcounteren[3] AND scounteren[3]. This yields seven legal
zero reads and five illegal-instruction traps with unchanged destination.
M EBREAK with medeleg[3]=1 must remain in M. U ECALL with medeleg[8]=1 must
reach the S vector-table base, not the interrupt slot. All phases return to M
through explicit, separately counted exit traps. No unexpected trap is accepted.

## SSIP Timing Boundary

S code enables SIE, then sets SSIP synchronously. The following 256 instructions
are exclusively 32-bit ADDI x0,x0,0. There are no loads, stores, branches, CSR
accesses or architectural register writes in that window. A timeout is failure.
The S handler records the original sepc, requires cause interrupt|1 and slot1,
clears SSIP and SPIE, and writes a fixed resume PC before SRET. Raw EPC is retained
in the snapshot; no instruction outside the window may be omitted.

Spike and RTL can retire different NOP-prefix lengths before SSIP delivery.
The ordinary full scalar comparator is NOT automatically qualified for this
case; zero trap or generic prefix acceptance must not be substituted.

A future strict admission must first run the unmodified full comparator. If it
does not match, only a reviewed, case-specific finite stuttering comparison may
accept the difference. It must independently verify each complete trace:

- Exact ELF bytes prove the entire window is inert and fixed-size.
- Window retirement is a single contiguous prefix; interrupt EPC equals the
  next unretired NOP, not merely any aligned address inside the window.
- Exactly one SSIP event, correct pending/enable/delegation state, correct vector
  slot and handler instructions, and fixed SRET resume are proven independently.
- Handler sepc reads and the resulting snapshot stores carry each trace's own
  proven EPC. Only an explicit PC/register/store allowlist for that value may
  differ; validate every propagation and forbid any other data dependence.
- All other instructions, GPR/FPR writes, CSR effects and memory effects compare
  exactly in order, including all synchronous traps and all exit traps. Neither
  signature equality alone nor dropping handler instructions is sufficient.
- Full terminal/tohost, exact225 checks, raw trap population, pending-clear,
  destination preservation and configuration restoration are mandatory.

The preflight has NOT implemented or approved that cross-trace comparison. It
only verifies Spike and saves the complete trace and raw EPC for parent review.
If precise propagation or retirement evidence is unavailable, DUT admission
must remain blocked rather than ignore an interrupt mismatch.
