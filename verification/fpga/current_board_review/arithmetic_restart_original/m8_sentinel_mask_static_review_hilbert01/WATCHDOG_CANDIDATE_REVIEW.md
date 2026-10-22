# Frozen M9 Watchdog Candidate

Decision: NO_BLOCKER_DIAGNOSTIC_CANDIDATE_ONLY for exactly `+COMMIT_WATCHDOG=1000000`. Recommend inclusion in the pending single e16/m8 worker plan, subject to exact-plan review and parent's separate runtime admission. No launch authorized here. No RTL change, trial execution, alternative values, or budget extension.

## Actual semantics

Reviewed frozen `/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources/`:

- `hardware/tb/ara_commit_monitor.sv` SHA256 `38b7642703c49e31fd0493b81e948388f2dbc72f97da418f3ed76e73bd42c782`: lines75-76 enable only with nonzero plusarg; lines146-148 progress is accepted req handshake, accepted resp handshake, backend alloc or any backend done. Lines248-249 additionally include any valid RVFI retirement. Mere request presentation, arch_start, outstanding work, MMU traffic or AXI beats alone do not reset this counter.
- Lines303-308 flush commit output (and vector output if opened) on each progress cycle. This is fflush, not fsync/power-loss durability. An arch_start without a progress event may remain buffered; do not claim every event has immediate durable publication.
- Lines311-321 reset idle on progress, otherwise fatal at the millionth consecutive no-progress clock. Progress on the threshold cycle wins and resets. Diagnostic supplies last retired PC/insn and monitor cycle, not necessarily the blocked instruction or root cause. This is simulated-cycle silence, not a wall-time watchdog.
- Continued scalar retirements or repeated backend activity can mask a stuck individual owner. Existing exact owner/generic checks and fixed external timeout remain necessary. A fatal is failure, never a successful partial-prefix acceptance.

## Basis and limits

Frozen `hardware/src/ara_soc.sv` SHA256 `41268269246a564bec870bab1a45bdb260786ffa95d2f50cb912cc61792d3e62`: L2 converter at218-237 has `mem_gnt_i(l2_req)` (always available); line329 registers l2_req into l2_rvalid. The SRAM initialization string random concerns contents, not randomized service latency. Lines645 onward use the fixed response delay. Frozen `hardware/tb/ara_tb.sv` SHA256 `c6416eabbc9a77c49ffbaec4643dcafdc1a31e758a35f1418cf084d63049f3e8` sets ClockPeriod1ns and AxiRespDelay200ps at748-750. Thus the ordinary local memory target does not intentionally withhold service for a million cycles. These local facts do NOT constitute a formal end-to-end arbitration/queue/translation fairness bound.

Existing `full_e8_m8_timeout_analysis01/closed_prefix01/REPORT.md:79` reports largest recorded all-event interval6352 cycles, retirement gap6354 and a completed6378-cycle owner. One million is about157 times the recorded event gap. This is evidence from the completed e8/m8 prefix, not an exhaustive e16/m8 maximum or a proof excluding all legitimate long gaps. An arch_start counts as a recorded event but is not alone watchdog progress, so the metrics are not identical.

The old timeout lacked COMMIT_WATCHDOG and its progress-triggered flush. Its absent final simulator-cycle/tail evidence cannot distinguish late silence from continued slow progress. This candidate addresses that observability gap; it cannot retrospectively diagnose the old timeout.

## Admission and expected outcome

Keep case10800s and existing worker/service bounds unchanged. Per-progress fflush can add substantial filesystem/syscall wall cost across millions of retirements; no measured overhead or <=3h guarantee is available. Simulation-time threshold does not bound how quickly a slow host reaches it. The reference firmware reduction alone cannot compensate or establish runtime admission.

The final plan must bind the same M9 image/monitor and exactly one watchdog plusarg, preserve trace/NO_FSDB and functional checks, save actual numeric child exit before postchecks, and retain fatal/timeout as failure. No retry or threshold increase on fatal. If fatal occurs, use the closed trace and last-PC/cycle diagnostic to formulate hypotheses; neither fatal nor remaining event activity identifies the root cause by itself.

Review performed statically only; no active trace read, reference, Host test, DUT, or process polling.
