# Actual M9 Startup

Hilbert entry REVIEW.json fd037688c41dce7efd371e82aed37534ee00588391f1f71c44c7da7bb128c764
binds plan57d3d71260ae7b06f2bd6498ab9246bf1e4cbc9146935a916bc6d39ca9139ca8.
One service submission succeeded; launcher actual exit0 (exec final042233).
Service ara-arithmetic-full-e8-mf4-m9-01.service, MainPID2857864,
actual frozen-M9 simv2857934 in that exact cgroup/private ELF/trace output.

Fresh admission: seven external simvs plus this one =8 of24; reserved0;
MemAvailable116968259584 bytes, above32GiB. External jobs untouched.
Two fixed startup samples5.10s apart: CPU ticks538 to1044, CSV221184 to507904
bytes. Saved startup_observation.json reports LIVE_CPU_CSV_GROWTH_CONFIRMED.
These are startup facts, not DUT acceptance. No later simulation polling.

Output prepared01/; local service.log and replay/tests/arithmetic_full_e8_mf4/.
Case10800s, worker12000s, service13200s; first failure stops, no retry.
ExecStopPost saves actual service_exit.json then invokes pinned collect.py once,
producing collector_result.json and actual collector_exit.json. It verifies
durable numeric child0, strict full oracle/20592 required owners, generic trace,
input/evidence pins and actual service exited0/success; failure remains NOT_ACCEPTED.
Prior plan01 HOLD/source/reference/RTL remain unchanged. Full4095 source-port,
not original Linux execution or full22-shape closure.
