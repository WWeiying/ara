# Whole1134 M9 Entry Review

Decision: **NO_BLOCKER_ENTRY_REVIEW**, for the exact plan and launch conditions
bound in ENTRY03.json. This is entry clearance, not DUT acceptance.

Plan: `d8e001aac8fe165f987e9fac9ded30e38c61233d240a5f4d439c7081b2a51d0d`.
Actual read-only hashing checked all743 input pins, zero drift, process exit0.
No Host, reference or CSV semantic audit was repeated.

## Owner And Source Semantics

- Frozen M9 dispatcher whole-load decode overrides invalid CSR layout and zeroVL;
  effective length uses encoded EEW. Mode4/VILL whole loads therefore remain
  valid. Whole moves use current SEW for architectural EVL/start comparison;
  original source excludes mode4 moves.
- Actual ELF helper windows contain two vstart-zero vl8re8 preloads, the original
  target, returned-vstart observation and vstart-zero vs1r/2r/4r/8r readback.
  Readback is not always eight registers. Exact PC/code/branch/arguments and
  scalar setup/CSR tracking are checked.
- 4536 payloads require3402 staging/readback owners and864 nonempty targets:
  total4266. The270 empty targets may legally have no backend owner. No fixed
  allocation count is imposed beyond required owner presence and completion.
- These aligned admitted original cases have no allowed-exception branch.
  This review does not impose an owner requirement on hypothetical legal faults
  outside the source scope.

## Existing Host Evidence

Host02 actual exit0,143.756s:12 tests, full1134 synthetic actual-PC positive,
1233792 byte checks and21366 helper instructions. Every4266 required owner's
complete alloc/done pair deletion is rejected. Missing full fresh-init interval,
input/result/guard corruption, vstart/status, owner identity, ABI/reset and
completion-cache mutations are rejected. Worker02 five real subprocess signal
tests pass, including before-publication, rename and deadline aborts.

Host01 remains NOT_PASS: fixture selected an actual sb-zero instruction with
nonzero synthetic UART data. Host02 corrects fixture register selection and
list-index reporting only; no oracle/checker weakening.

## Runtime And Closure

The actual numeric child result is durable before artifact validation.
One closed-CSV fanout supplies unchanged rows to the frozen generic protocol
validator and strict full-source observer. No suffix reset or partition is
introduced. Late disk-pin checks and terminal abort latch remain enabled.
ExecStopPost records actual systemd environment, not collected-unit defaults;
the hash-bound collector separately persists its actual process exit.

The sole launch must add `--property=TimeoutStopSec=360` before the worker
executable and retain the exact actual command receipt. This accommodates
the300-second metadata collector without changing case10800, worker12000 or
RuntimeMax13200. Keep sealed plan/ready/scripts unchanged. Owner must retain
successful prepared dryrun and perform the existing resource/identity checks.

Reference4348773 instructions and8397.635-second projection support the bounded
attempt, not a completion guarantee. No automatic retry or timeout extension.
Actual DUT/worker/collector outcomes remain required for acceptance.

