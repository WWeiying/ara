# Quantized Attention Retirement Diagnostic

## Question

The accepted six-call Q4 and Q8 H/S/B results establish complete operator
correctness and latency. They do not identify all remaining software work.
Subtracting QBS engine busy time from application cycles is not a stall
breakdown. This diagnostic supplies the missing architectural retirement
evidence without changing hardware or replacing those accepted measurements.

H is the head-major RVV schedule, S shares KV work across heads using RVV,
and B uses the shared schedule with native QBS QK computation. All three
include query quantization, online normalization, value decoding and PV.

## Evidence Gap

The accepted canonical Q4 worker's `simulation_command` enables VECTOR_TRACE
but not COMMIT_TRACE. Its vector CSV contains neither scalar retirement PCs
nor the destination values of the cycle CSR reads. The equivalent Q8 trace
has the same limitation. Backend completion events are not architectural
retirement and cannot replace these missing records.

The existing `hardware/tb/ara_commit_monitor.sv` already emits scalar RVFI
retirement with a contiguous order, PC, instruction, destination register and
destination data when COMMIT_TRACE is enabled. The accepted canonical image
contains this monitor. No RTL or hardware build change is required.

## Bounded Experiment

- Run one fresh diagnostic ELF, in H/S/B order, with the original real Q4_0
  keys and Q8_0 values: six query heads, dimension 128, 128 visible tokens,
  K token stride 144 bytes and V token stride 272 bytes.
- Keep the original computation, production primitive objects, inputs, output
  checks, guards, FCSR/VCSR checks and expected work. Change only the number
  of diagnostic calls and the explicit diagnostic completion protocol.
- Three calls do not establish mirror-repeat reproducibility. Do not print
  or accept a repeats-exact claim for this diagnostic. The already accepted
  six-call experiment remains the performance/repeatability evidence.
- Use the accepted actual canonical VCS image, COMMIT_TRACE, VECTOR_TRACE and
  the independent events/backend/AXI/AXI-write checks. Pin input, ELF, helper
  and image identities before and after one bounded attempt.
- Bound the simulator at 10,800 seconds; no retry or timeout extension.
  Three calls limit trace overhead while retaining a full invocation of
  every schedule. Do not shorten tokens, heads or dimensions.

## Interpretation Contract

1. Recover cycle CSR instruction sites from the actual linked disassembly.
   Match their retired destination values to each printed application cycle
   measurement, modulo 64-bit arithmetic. Validate instruction bytes, traps
   and contiguous architectural order; count only retire events.
2. Report scalar (including scalar FP), RVV (including configuration), and
   custom instruction counts, with explicit function and mnemonic counts.
3. Attribute software residence only where PC/function identity proves it:
   query quantization, RVV dot product, value decoding, scale/MAD, exponential
   helper and native-command submission are candidate named contexts.
   Main/runtime functions contain inlined work, including admission, gather
   and online normalization. Keep such intervals grouped or unclassified
   unless an additional exact machine-code mapping proves the finer label.
4. A gap between retirement events is not an execution-unit utilization or
   exclusive stall counter. State the interval-assignment convention and
   retain unassigned boundaries. CSR execution and retirement occur at
   different times: report monitor-cycle span and application CSR delta
   separately, rather than forcing an artificial equality.
5. Bind native command retirement and engine work to eight QBS commands in
   B, none in H/S. Keep engine busy activity separate from software residence.
6. Fail closed on incomplete retirement windows, unknown executed instruction
   bytes, wrong outputs/work/CSRs, trace truncation or source/image drift.

## Ownership and Status

`prepare/`, `analysis/` and `worker/` have separate implementation owners.
Original accepted workers and checkers remain frozen; the successor must
not relax their checks. At creation of this plan, preparation and host tests
are in progress; no diagnostic VCS execution or attribution result is claimed.

Out of scope: another hardware optimization, whole-model speedup, Q8 phase
equivalence, synthesis, PPA, FPGA or default-on deployment.
