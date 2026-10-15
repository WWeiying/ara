# Independent Pilot Failure Triage

Status: **MEASURED_DUT_ADDRESS_FAILURE; RTL mechanism not yet wave-proven**.
Read-only raw CSV/log/source investigation. No test, simulation, RTL/helper
edit or retry. Original prepared02 NOT_PASS/aborted=true and controls NOT_RUN
are preserved. The earlier review allowed measurement, not DUT acceptance.

## First Error

Actual full-oracle firmware mismatch, not checker rejection or timeout:
628.632833s, rc255, failure-marker cancellation; case limit4200s not reached.
Raw `console.log:510` and `work/run.vcs.log:508` report check160, round0:
expected `0x0000000040017000`, actual `0x0000400040017000`.

Independently streamed raw CSV and reconstructed scalar registers at check():

- First mismatch: CSV line299437, cycle368106, check PC `0x8000007a`.
- Original target PC `0x80000d64`, opcode `0645f207`.
- 17 faulting target accepts; 16 completed normal fault MRETs, last at
  cycle367637/PC `0x80000c90`. No successful target/checkpoint before failure.
- Faults0..15: cause13, same mepc, starts0..15, original mtval sequence correct.
- Attempt16 starts at arch_start cycle367643 (seq102), accepted request and
  exception response at cycle367681. Cause13 read at PC `0x80000612`,
  cycle367802; mepc at `0x80000616`, cycle367804 is `0x80000d64`.
- The first wrong architectural CSR is **mtval**, retired at PC `0x8000061a`,
  cycle367806 (CSV line299158): `0x400040017000`.
- Subsequent CSR reads: vstart16 at cycle367810, VL32 at367811, vtype17
  at367814, fcsr117 at367816, vcsr5 at367820. These fields are correct.

Thus the wrong address already exists in a real machine CSR before firmware
compares it or prints anything. It is not a printf width error or Python gate
inventing a value. Strictly observed scalar stores reconstruct all256 index
bytes; all32 values match original `((i*13+7)%32)*4096`, including
index16=`0x17000`, index17=`0x4000`. Initial SNAPSHOT capture logs show all32
original EEW64 words correct, including lane0 word4=`0x17000` and lane1
word4=`0x4000`. The first replay logs only word0/1; they do not prove the
vstart16 request's operand origin/layout. Sv39 fault policy is different from
Linux, but expected VA is valid within the fixture's original mapped extent.

## Discriminating Hypothesis

The erroneous offset is exactly `(index17 << 32) | index16` =
`0x400000017000`; adding base `0x40000000` gives measured mtval exactly.
The frozen four-lane EW32 shuffle table (`ara_pkg.sv:546`) selects bytes0..3
from lane0 and bytes4..7 from lane1's low32. Applying that layout interpretation
to the logged original EEW64 packet reproduces this error without arbitrary
bit corruption. It strongly suggests index physical-layout/metadata mismatch
at the v4->v5 source boundary (VLEN1024 gives16 EEW64 elements/register).

Trace the request, not just snapshot-valid clearing:
`ara_dispatcher.sv:4236` selects old_eew_vs2 from the active source register;
`:5578` sets replay and `:5584` overrides old_eew for a retained VLXE source;
`:5923` has snapshot-valid consumption logic. `ara_sequencer.sv:775` propagates
both EEWs. `addrgen.sv:292` concatenates lane operands and `:296` deshuffles
using pe_req_q.old_eew_vs2, then `:470` adds scalar base to index. The raw logs
cannot distinguish bad replay/layout selection from a physical operand read
or later MMU/CVA6 exception-tval corruption. No unique RTL fix is authorized
by this note; measure that boundary first.

## Wave Timing Correction

Do not assume `%0t=3574300000` means3574300ns. Actual compilation options in
`novas_dump.log:142` use `-timescale=1ns/100fs`; Tesla's exported VCD header
independently reads100fs. TB ClockPeriod is1ns, matching monitor~357k cycles:
the capture print converts to **357430ns**, not3.574Mns. Tesla also reports
FSDB summary max tag3709495000 at100fs =370949.5ns. The raw log never reaches
INDEXED_PROFILE_CLOSED_AT_1000000NS because firmware failed before that bound.

This is not proof of a complete first32-fault-round probe (only17 faults ran).
This reviewer has not decoded target wave values yet and makes no such wave
claim. It does invalidate the simple assertion that first1Mns necessarily
missed the target. Prefer offline existing-FSDB extraction around
357000..369000ns before spending another DUT run; Tesla owns that extraction.

## Only If Existing Signals Are Insufficient

Prepare a fresh profile, never edit capture.tcl/prepared02. Reuse exactly the
same M5 image and SoC ELF/full50-round oracle, with no software hints/forces.
Use Gather's delayed UCLI pattern: run without dump to350000ns, enable focused
capture, run to375000ns, disable/flush; log both actual capture bounds and
cycle_q. This includes initial source capture, correct starts0..15 and failing
start16 in a single25us window. No new run is requested by this analysis.

The decisive layers are:

1. Dispatcher accepted backend request: op/vstart/vl/vd/vs2, eew_vs2 and
   old_eew_vs2; snapshot valid/eew/replay flags; eew_q[4:7], reshuffle state and
   accepted maintenance writes. Separate combinational decode from handshake.
2. Four lane SlideAddrGenA: accepted operand_request, queue command EEW,
   source_snapshot_replay_valid/index, snapshot versus actual VRF data,
   operand_queue_input, queue output and ready/valid consumption, VRF address.
3. AddrGen: accepted pe_req and latched pe_req_q, addrgen_operand_i/valid/ready,
   shuffled_word/deshuffled_word/reduced_word, word_lane_ptr/elm_ptr/count,
   idx_vaddr/final/spill handshake and scalar_op. This locates the first bad
   `0x400000017000` before MMU rather than inferring it from mtval alone.
4. MMU request VA/valid, exception address/vstart, sequencer response,
   dispatcher acc_resp exception/tval and CVA6 cause/mepc/mtval write path.
   Existing VLDU actual grant/data/BE shows whether writes perturb the index
   source before retry; preserve correlation to instruction/transaction ID.

If operands are original EEW64 but old_eew is EW32 and the AddrGen result is
already bad, the metadata/deshuffle hypothesis wins. If operands are already
bad, investigate snapshot/VRF/queue upstream. If AddrGen/MMU VA is correct but
exception tval is bad, investigate response/CSR transport downstream. Correct
starts0..15 provide in-run controls; do not substitute arbitrary reduced data.

## Raw Evidence SHA256

- Private SoC ELF: `5a73bf57dc9d9cef6136ec8daa53e409c77abd5e0e47645d403392df5310347f`.
- Raw CSV: `aa349e129152a28ad166eeb627db298ebf9d869a7804d6e59344c4df725a1ee9`.
- Console: `e9d85a439655117db4d784a57ca1f35a673a02e9170f9c444b5ad8f0705327c0`.
- run.vcs.log: `8abafbed359bc7f19fd6511b249e1409a48115bab221f66ac1d031e68a4f7c71`.
- FSDB: `097b549514adaf71d680a96ce1b243eee115ebf8f62335587c59f39a6cb81fe8`.

All raw files above are beneath
`../vcs_candidate05_plan01/prepared02/pilot/tests/d32m2_i64_fault_ov1/`.
The frozen plan remains SHA256
`ab3b7fad17469a4fb317d7bcfaa0d7ca63e0b244fc6a4cb55cdf301f812e89c5`.
