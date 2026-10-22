# Terminal Rejection: Slide-Up No-Op Owner

Original run is NOT_PASS, not accepted. No DUT restart, timeout extension,
active CSV read or second semantic parse was performed. The event waiter
completed immediately when the already-closed terminal files appeared.

## Actual Terminal Facts

- Initial single observation: original unit loaded/active/running, MainPID2971257;
  child numeric0/10573.338762348s, no timeout/failure/cancellation; complete and
  collector files absent. Its live Result=success was not used as exit proof.
- Producer subsequently published NOT_PASS/aborted=true. Child remained0 but
  postcheck status ERROR. pins_unchanged=false is the unfinished terminal gate,
  not evidence of an actual pin drift.
- Actual original ExecStopPost: SERVICE_RESULT=exit-code, EXIT_CODE=exited,
  EXIT_STATUS=1. Collector actual wait1/0.266948s, NOT_ACCEPTED.
- Independent event-triggered metadata audit actual wait1/0.166179s, no timeout,
  firstcause: producer not complete PASS/noabort/unchanged/noretry. All failed
  receipts and the original sealed worker remain unchanged.

## Exact First Cause

Producer recorded missing necessary owner at zero-based call1200 (original
ordinal1201), retire_order771538, arch_order13209, helper_index8, alloc0/done0.
Instruction0x38813c57 at0x80000fd6 is original `vslideup.vi v24,v8,2,v0.t`.
Existing sequence.json gives seed0/op19/li1/mode0/VL1/start0. No raw trace was
needed to identify this tuple or original compiled instruction.

Frozen M9 dispatcher sources/hardware/src/ara_dispatcher.sv:2329-2340 decode
the unsigned VI stride and set null_vslideup when stride>=csr_vl_q. Lines5970-
5978 explicitly respond locally and set ara_req_valid=0 for null_vslideup.
Thus offset2/VL1 correctly needs no backend owner. Current checker instead marks
every target with vstart<VL as necessary, over-classifying this original no-op.
Measured missing alloc/done and the exact frozen RTL agree on a checker owner
qualification mismatch, not evidence of a numerical RTL failure.

The error occurs after strict.finish in the existing audit control flow, but no
final accepted strict report was persisted. This is not a substitute for a
successful independent whole-program acceptance. Original NOT_PASS stays intact.

## Next Step, Not Executed

A narrow independent offline successor may qualify this actual VSLIDEUP.VI
target using unsigned offset and VL as well as vstart, retaining all mandatory
helper owners, nonempty targets (including op24), full data/oracle and protocol
checks. Add exact no-op and still-required target pair-deletion negatives first.
Only an explicitly authorized closed-CSV recovery could then accept this run;
no rerun of the simulator is needed merely for this checker mismatch.
Active related workers were notified to preserve their sealed files and runs.

## Terminal Hashes

- complete.json:87129dd1db4b2b870d31faaff1c2ced706ad013807d49f09a7d4c45ffd27aa0a
- service_exit.json:cc7b1ccae6993e7b1aeef6532fce6134219ae2110beb1c01698d82f93f0cff4c
- collector_result.json:f7d5b39417645ecfe95801e785d289dd18ef171902eed3dfbc3b7c7f689a7baf
- collector_exit.json:040c8107c29dee360d8c102e451ab488c1ca16fdfc7067f906fe3144de3e58ef

All four paths are under full_e8_m4_dict_vcs_m9_plan01/prepared01. Independent
wait/actual audit exit/result/report are under this directory's terminal01.
