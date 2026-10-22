# Startup01

Status: STARTUP_PROGRESS_CONFIRMED_NOT_DUT_PASS.

- Plan SHA256: ffdf6ce4cede184c6dc5ff817f7bb3ed92913ca91da28dddaaec54580e746f6c
- Exact copied Zeno entry binding SHA256: 593ab1cb22fb5caddfc57928bd24321e6413f9fc95d158c895c224b58666d99e
- Prepare, dryrun and the single systemd-run invocation each exited 0.
- Unit: ara-fp-alias-original682-m8-01.service; direct worker PID 2079912; M8 simv PID 2080328, same control group.
- Service active/running at observation; RuntimeMaxSec 13200, KillMode control-group, Restart no. Simulation limit remains 10800 seconds, jobs1, no retry.
- Exact M8 simv path/private ELF command captured in STARTUP01.json; private ELF SHA256 9a541b0d10d243b02b14136accb65bb9e9d3dcc4b18716c96239e719adaa5044.
- Over 3.004920 seconds, simv CPU ticks 4184 -> 4482 (100 ticks/sec; 99.17% CPU), CSV bytes 1933312 -> 2093056 on unchanged inode 27858018605.
- These are CPU ticks and file-size progress, not a claim of decoded trace-cycle advancement. No active CSV contents read.
- Full original682/681-predecessor execution remains pending. Existing worker automatically performs strict full-oracle plus generic/lifecycle checks, persists actual monitor exit before postchecks, and publishes its terminal result. Startup does not establish DUT PASS or historical service exit.
- No further startup polling, duplicate launch, RTL/build changes, or changes to consumed code/pins.
