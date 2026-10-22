# Single M9 Launch Confirmed, Not DUT PASS

Unit: `ara-arithmetic-original-e32-m2-full5985-m9-01.service`.
Worker3353245, actual simv3353284; one launch, launcher numeric exit0.
Output: `prepared01/`; local append log: `prepared01/service.log`.

Exact plan a5685d503e6f8a422b3e7938b9c86a0e155157d4ebbf2c7774c9c15e2f23de5e,
903 pins. Independent entry NO_BLOCKER result
48f1a47e394ce576834a13104e5ece06a76250a02ef7d1c396c7a410411984ec.
Fresh admission:1 external actual simv +1 own job +0 reservation =2<=24;
MemAvailable178690367488 bytes >=32GiB. No external task changed.

The sole startup observation sampled the same executable/PID/start ticks/cgroup
and matching private ELF b9a09a69f9ae8d93b38f5a3f8de1049967a79127ebb473da7f321e73143039f6.
CPU ticks864->1370; CSV bytes393216->663552 over5.104 seconds.
No active CSV contents read. Actual systemctl returned0 and showed active/running,
MainPID3353245, and exact ExecStopPost exit_hook.py/output attachment. This
confirms attachment only; it does not fabricate a future service exit or PASS.

`prepared01/startup_observation.json` SHA
f5bb8fda5aa72016f7138087031bb7a4da80d5740991fb8e95de22ef8bb0c6c9.
`prepared01/launch.json` SHA
51966ccb668c46b7619a5e7f758f4a88288e78ace1c837700e729ca523e268e7.
`prepared01/service_submission.json` SHA
7efa968fc513b9f484b3f808174da6618786f77df1ec9e7dd0865ecb6bc888a8.

Host02 actual0/474.644976s/all35 tests/full5985 constructed stream passed.
Host01 remains incomplete, deliberately stopped with actual-15 after251.969013s;
the locator-only successor diff and both outcomes are pinned, not overwritten.

Fixed case10800/worker12000/service13200/jobs1; no retry. On actual exit, the
frozen hook records systemd environment and runs one bounded metadata collector,
requiring numeric child0, full oracle/owners/generic trace and unchanged pins.
Scope remains5985 continuous source-derived calls,383040 uint32 results,
11970 guards,197505 packed reads,1890 fresh FP setups; original no fflags oracle.
2205 ordinary vstart no-ops and18 additional exact VI2 no-ops are separate.
No further polling after this receipt, no Linux historical closure claim.
