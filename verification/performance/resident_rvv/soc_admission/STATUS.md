# Experimental Resident PV Integration

## Purpose And Boundary

The accepted software control already alternates the replayed V-row registers.
The next experiment removes the per-token VRF replay and accumulator round trip
by reading the existing AKV V context and borrowing each lane's existing FP16
FMA interface. It does not change AXI width, DDR, frequency, lane count, or the
number of arithmetic units. The private accumulator capacity is 16 x 64 bits
per lane, 512 bytes across four lanes; this is additional storage, not free
reuse of the architectural VRF. No synthesis or FPGA acceptance is claimed.

Production admission is opt-in with `ARA_AKV_RESIDENT_PV_ENABLE`. Capability
index 4 remains zero even in the experimental image. Existing applications
therefore cannot select this path through capability discovery. A reviewed
experimental wrapper must explicitly issue it. The normal RVV implementation
remains the software fallback; production SDK and llama.cpp integration require
subsequent numerical and complete-call performance acceptance.

## Instruction And Ownership Contract

- Custom-2 opcode `0x5b`, funct3 7, funct7 2. Existing column instructions keep
  their encodings. `rs1` supplies a nine-bit control word; encoded `rs2` is a
  vector source, not a second scalar operand. The instruction has no scalar rd.
- Control bits 5:0 encode T-1, bit 6 encodes H-1, and bits 8:7 select D64,
  D128 or D96. T is 1..64 and H is 1..2; upper bits and other D codes are illegal.
- The source group is aligned to eight vector registers, with the first six
  EW16 registers read: two fixed-stride seed rows and packed coefficient pairs.
  The independent source interval is 384 halfwords, not destination VL256.
- The four-register destination is aligned, wholly disjoint from the reserved
  source group, and clobberable. Head stride is 128 halfwords; only active D/H
  output is defined. Register EEW tags update only after successful completion.
- The operation requires four lanes, VLEN1024, FP16 support, legal frm,
  vstart=0, FP/vector enable, and the existing consistency admission. It does
  not change architectural VL or VTYPE. Source preparation remains ordinary RVV.
- Admission waits for ordinary VLSU/context work to drain. The accepted CPU
  request and transaction identity remain held until the terminal response.
- Lane acquisition observes actual operand-requester `state_q == IDLE`, queued
  and returning operands, VMFPU idle, and native LDU write debt. The requester's
  ready signal acknowledges a valid command and is not an idle indication.
- Seeds and coefficients arrive over StA. Resident V words reuse the existing
  LDU payload wires but do not request VRF writes. Arithmetic and accumulator
  state stay local to each lane.
- Commit requires complete source drain, resident-reader completion, and every
  lane's result barrier. Only then may local results use the normal LDU write
  port. Final VRF acknowledgements must drain before FPU release and CPU reply.
- Pre-commit errors discard/drain work without publishing destinations or new
  flags. A protocol violation after irreversible commit is fatal, not reported
  as a recoverable partially completed instruction. No asynchronous LSU-only
  flush during the blocking lease is supported.

## Evidence At This Checkpoint

The component full-stream experiment passed 66 normal executions and three
guard executions on the real VMFPU interface. It checked source import, FMA
results, cancellation and final acknowledgement. This is not SoC acceptance.
See `../pv_fullstream/RESULTS.md` for original evidence and exclusions.

The unchanged-SoC preparation diagnostic passed real Qwen3 D128/H2/T137
(64+64+9) calls. Mean issue interval was 577 cycles and mean diagnostic
issue-plus-dump interval was 907 cycles per complete call. These include
instrumentation and do not equal the new instruction's preparation cost.
See `../pv_prepare/RESULTS.md`; no hardware performance gain follows from it.

Host checks at this checkpoint:

```sh
python3 -B scripts/gen_akv_abi.py --check
python3 -B verification/performance/resident_rvv/soc_admission/abi_test.py
python3 -B verification/performance/resident_rvv/soc_admission/geometry_test.py
python3 -B verification/performance/resident_rvv/soc_admission/lane_owner_test.py
python3 -B verification/performance/resident_rvv/soc_build/test_build.py
```

ABI: 14 tests; geometry: 8 tests; build harness: 18 tests. The lane-owner
host script reports 2919 property assertions, including 297 assertions binding
the requester-idle regression to real source. These counts are not independent
RTL test cases. All passed; SoC RTL execution remains pending.

## Next Acceptance Gates

1. Build from the accepted frozen dependency/testbench closure plus the explicit
   production RTL overlay. Pin both original and copied files; preserve failures.
2. Run a short real-data SoC case with discriminating ownership/source/write
   probes before the complete ABBA call. Check terminal, CSR, destination,
   untouched groups, exact FMA counts, source drain and actual final writes.
3. Exercise legal D/H/T tails, invalid admission and context reuse, plus ordinary
   RVV/QBS with the experimental feature enabled. Keep error evidence separate.
4. Compare the whole real-model call with the stronger rotated software control
   in the same binary and co-layout. Include preparation, acquisition and drain;
   a local arithmetic latency is not a complete-call speedup.
5. Proceed to shared QK scheduling and runtime selection only when measured
   benefit justifies the bounded storage/control cost. QK must preserve widened
   FP32 accumulation and reuse the accumulator store rather than add a MAC array.
