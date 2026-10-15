# e16/m8 Sentinel Terminal Failure

Verdict: NOT_ACCEPTED_ACTUAL_CASE_TIMEOUT. No full4095 DUT acceptance; ledger remains18/22. No retry, extension, RTL change or CSV semantic scan performed.

Evidence root: `full_e16_m8_sentinel_vcs_m9_plan01/prepared01`, exact plan SHA256 `0a2820506439278384569a58f72b76fcb72ae5276f4f302ba6a31f0c65a6335e`.

## Actual Cause of Termination

`replay/tests/arithmetic_original_e16_m8_full4095_sentinel/child_outcome.unvalidated.json` records actual numeric return255, elapsed10800.076115955133s, timed_out=true, failure_seen=false, cancelled=false. SHA256 `81c13f8de5abc3a5e90b7f3ba57df05d638546f9942d8067f97dffefff411a6f`.

The actual pinned M9 frozen `verification/ara_verify/runner.py` SHA256 `6c7ef9032d000d279d1e0c3b32f8a36e28faee1af69adb4b1e6f821354099e8e` matches its plan pin. Its monitor sets timed_out at the wall deadline, stops the private process group, and waits for process exit before returning. The wrapper saves this outcome before setting sticky abort. The runner then checks cancel_event before its TIMEOUT branch, so the public result becomes CANCELLED. Thus CANCELLED is downstream presentation of this timeout, not evidence of an independent initial cancellation. Return255 is the actual post-stop numeric result, not an original numerical-error exit.

`complete.json` SHA256 `b5594fd289ea599278e25a576ec2e8629eeed47c31905e6af1ee1ef1c80664a3`: NOT_PASS, Sticky abort, aborted=true, retries0. pins_unchanged=false means successful late-pin qualification was not reached; it alone is not proof of pin drift.

`service_exit.json` SHA256 `34c9869e4b7ee3349e679d8af28d6cc7de215ae67d0b524490cae7199efeb80a`: actual exit-code/exited/1. Collector correctly rejects at its service-success gate; its firstcause is not the underlying simulator cause. `collector_exit.json` SHA256 `e9c75fcd278ea6fad6d9c522a82569c2c5ac1d22895839ebfea06b2c18dc9714`: actual child wait1/0.280237s, no timeout. The separate event observer exited success/0 and explicitly claims no DUT acceptance; observer success is not service/DUT success.

## Closed Evidence and Limits

The durable monitor wait and later service/collector terminal receipts establish that the managed simulation writer was stopped before bounded log inspection. No live-process query was made. Read only service.log tail<=10000B and console/run.vcs.log tails<=6000B each; actual console sizes1277B/1632B mean those bounded reads cover their entirety. No watchdog fatal, numerical error, or PASS appears there. Service log shows START watchdog=1000000, SAVED rc255, CANCELLED, NOT_PASS. Exact actual command SHA256 `f332029fa42ce386629d80b558ebd32fd78dfb267b7e61cee0d2f76944c5ecde` includes the approved watchdog and private ELF.

No `strict_original.json` or `trace_summary.json` exists. Consequently failure_seen=false is not a numerical-correctness proof, and no full oracle/owner acceptance occurred. CSV exists at296607084B (stat only; not read or hashed). A million simulated no-progress cycles did not produce a recorded watchdog fatal, but this does not prove continuous useful progress: active livelock can reset the watchdog, or host wall timeout can arrive before a final silent million-cycle interval elapses. Last instruction/call, remaining work, end-of-run progress and possible numerical mismatch are presently unknown.

## Proposed One-Pass Diagnostic, Not Executed

Only if separately authorized: one closed-file pass, fixed <=600s, no retry, no Spike/VCS, with numeric wait receipt saved first. Bind original plan/ELF/profile/checker/model and raw device/inode/size/mtime/ctime before/after; compute raw digest in that same pass. Preserve malformed final-record evidence instead of silently dropping it.

Use the reviewed generic token observer plus strict model to validate completed calls and all fresh/oracle obligations through the prefix; explicitly permit only an unfinished EOF state for diagnostic reporting, never PASS. Do not call the full4095 acceptance finalizer or waive earlier errors. Stop on first semantic/protocol error with exact row/cycle/PC/instruction/call/model state. At EOF report completed-call ordinal, active call/helper/output-read state, pending owner IDs, last progress cycle, largest progress gap using the actual monitor progress definition (not arch_start alone), retirement/gap bins and exact final valid record. Output compact summaries, not the full call ledger.

This would discriminate prefix numerical/protocol error versus a clean but incomplete progressing prefix and identify unresolved owners at EOF. It cannot establish an unrecorded final simulator cycle or prove a hardware root cause. A closed tail/header spot-read could precede implementation only under that explicit diagnostic authorization. Zeno is not duplicating this review or scanning raw.
