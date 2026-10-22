# Actual Optimized E64 M1 Startup

The user's conditional single-run authorization was consumed after unchanged
source/helper proof, full Host/Spike/reference acceptance and the20%-margin
9199.936s estimate below10800s. No old parent/independent review was reused.

- Unit: ara-arithmetic-full-e64-m1-m7-01.service
- Actual direct worker PID1952913; actual frozen-M7 simv PID1953090.
- Active/running, Restart=no, KillMode=control-group, same unit cgroup.
- Plan SHA256: b3f3e4c4ee76ff2f950dcc53b1692c800fa05ae7cd540c7ade16631f5f34c765
-1587 pinned inputs; Host15 exit0/57.869218533s; actual dryrun1 exit0.
- One DUT case only; jobs1, simulator10800s, worker12000s, service13200s.
- Actual admission:6 external simulators+1 new=7,63269146624 available bytes.

Actual command uses M7 image, exact private optimized ELF, seed1, +NO_FSDB
and private commit_trace.csv. ELF contains the exact original-shape BEGIN.
At startup, console showed ELF loading/tracer creation, not yet BEGIN; no
functional progress or result is inferred from the static marker.

At Unix1791872001.4071906 simv user/system ticks718/21, CSV323584bytes;
at1791872003.4093268 ticks916/21, CSV425984bytes. Approximately98.9% CPU and
102400bytes trace growth in2.002s confirm execution. No active CSV content
was read. No further polling loop is started.

Worker persists numeric monitor outcome before postchecks, then runs complete
generic and original strict CSV validation, full oracle/order/guards and late
pins before terminal publication. This startup is not DUT acceptance. Failed
or timed-out output is retained without retry or budget extension.
