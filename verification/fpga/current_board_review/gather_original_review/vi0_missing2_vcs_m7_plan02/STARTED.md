# M7 VI0 Numerical Prefix Regression Started

User-authorized once-only service: `ara-gather-vi0-prefix112-m7-01.service`.

- Direct worker/MainPID1949525; RuntimeMax9600s, KillModecontrol-group, Restartno.
- Actual e8/m4 simv1949572: same PID generation282983726, CPU ticks182->247, CSV bytes20480->49152.
- Actual e16/m8 simv1949571: same PID generation282983724, CPU ticks194->260, CSV bytes20480->53248.
- Exact M7 simulator, runtime TESTCASE IDs, private PRELOAD ELFs, private work CWDs and paths were confirmed. Startup uses two positive samples inside one60s window, not a zero-baseline false confirmation.
- Actual systemd launcher exit0 is in `prepared01/launcher.actual.json`; owning service facts and launch resource admission are in `prepared01/launch.json`. Service exit is not yet known. The startup receipt is `prepared01/actual_simv_confirmation.json`.
- Plan SHA256: `1e4f0158e428efda28a652ba7e1958971fb971a16d48c4988aa353e141be7b8a`.
- Latest prelaunch resource snapshot had five external simv plus own two=seven; available61575618560 bytes. Zeno's additional two reserved slots still fit cap24. Worker rechecks resource admission before each dispatch, with reserved_slots0 (no obsolete quota charged).

Both source/reference prefixes are accepted, not yet DUT accepted: each112 original calls/111 predecessors, cap512,57344 results/224 guards/112 vstarts/1456 helper instructions; physical predicate128 and2178 scalar setup values retained. Measured firmware retired counts2560282/2390386 project conservatively to4267s/3984s at600instructions/s; budget is fixed9000s/case, not a promise.

No new RTL/build or reference execution was launched by this worker. First nonzero/timeout/failure marker or postcheck exception cancels only its own scope, preserving actual monitor outcome before generic checks; no automatic retry. Terminal result will be `prepared01/complete.json`, with raw evidence under `prepared01/replay/tests/`. No further long-task polling is performed.

The old prep/dryrun failures are preserved. This new scope is original VI0 numerical coverage, NOT an exact historical stopped tuple, NOT closure of any of11 archived stalls, NOT full2688 children, and NOT original Linux/parent execution. Decoder is separate at `../r168_context_decoder01/`; it requires actual matching regs+stack and produces no guessed tuple without them.
