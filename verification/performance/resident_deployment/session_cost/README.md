# Resident Linux persistent-session candidate

This successor removes per-call device open, GET_INFO and close from a warmed
worker. It does not change RTL, the kernel module, arithmetic, copying or the
model. The measured Linux speedup is not known yet. Resident remains opt-in.

## Runtime Contract

- `GGML_RISCV_AKV_LINUX_SESSION=1` retains one FD per GGML worker thread.
  Unset or `0` keeps the previous per-call interface.
- Every call still checks current vector permission and FD/V/Zfh/Zvfh support.
  VSTART and FRM are checked before initializing the thread-local session.
- GET_INFO is checked on opening. Every EXECUTE still checks the kernel device
  epoch, online CPU count and execution ownership. A retained FD is not a lease
  on the hardware context and does not retain K/V contents.
- Execution errors close the cached FD; the failed operation is never retried.
  Only a later independent call may reopen it. Partial results are not published.
- A worker closes its FD at thread exit. Stop the process before removing the
  module; do not force module unload. Fork inherits an FD, but executes still
  use the driver's shared lock and epoch gate. No cross-process hardware lease
  is introduced.
- Cold use adds an admission check before TLS initialization. Report cold and
  warm time separately. Warm calls remove three syscalls, not all Linux costs.

## Prepare

```sh
python3 verification/performance/resident_deployment/session_cost/prepare.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_board_pair_session_YYYYMMDD_01
```

This builds a frozen ELF from the delivery commits and explicit Linux/portal
overlays, tests the real client with syscall mocks, runs ASan/UBSan, and audits
RISC-V entry code. It reuses the checked call-cost kernel module only after
matching all its driver and compute sources. No live AKV assembly is imported.
Host tests and object audits do not establish FPGA performance.

## One-ELF Comparison

Keep the same bitstream and the cost-candidate module, with `profile=0`. Do not
replace either for this comparison. On the board, choose a new output directory
and verify `SHA256SUMS`. The intended three arms use the same ELF:

```sh
GGML_RISCV_AKV_LINUX_SESSION=0 ./resident-ggml-pair native 137
GGML_RISCV_AKV_LINUX_SESSION=0 ./resident-ggml-pair resident 137
GGML_RISCV_AKV_LINUX_SESSION=1 ./resident-ggml-pair resident 137
```

These are complete GGML calls, including conversion, packing when needed,
copying, driver and computation costs. Each process runs one cold and three
warm calls, checking exact outputs, flags, guards, fresh input and real portal
execution. Keep `RESIDENT_PHASE_STATS` unset for primary timings. Record the
session setting alongside the logs: the original PAIR JSON does not encode it.
Interleave the two Resident modes, then compare the winning mode to native;
do not compare a new warmed result to an old campaign's average.

## Remaining Work

The old VCS complete-call saving was 5,984 cycles on one representative input.
This is about 0.120 ms at 50 MHz, not a prediction for the FPGA memory system.
The latest Linux result is still slower than native. Reusing an FD alone cannot
establish a net gain: input copying, finite-value scans, state management and
syscall overhead remain.

The next structural option is a bounded, registered immutable input view or a
driver-owned mapped workspace, integrated with the GGML KV buffer lifetime.
It must not replace a removed kernel copy with another full user copy and call
that zero-copy. It also needs explicit handling of mutation, fork, unmap, device
removal and output publication. Page pinning alone does not make writable
user memory immutable. A whole-attention submission can amortize entry costs
across KV groups, but must keep IRQ-disabled work bounded. These are design
requirements, not implemented features of this candidate.
