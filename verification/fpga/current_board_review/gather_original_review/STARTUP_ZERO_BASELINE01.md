# Startup Observer False Cancellation

The first authorized Gather prefix2 run is not accepted. Preserve its sealed
plan, program inputs and `stall_prefix2_launch01/vcs_candidate04_01/` outputs.
This observation does not establish an RTL failure or a functional PASS.

`actual_simv_confirmation.json` records two genuine M4 simulators in the correct
service cgroup, with initially zero trace bytes and zero last_cycle. Discovery
then shows sustained CPU, CSV and cycle growth, reaching approximately53k and
55k cycles. Nevertheless confirmation returned NOT_CONFIRMED at60 seconds.

Static cause: `confirmation()` retains its original `before` sample throughout
the inner loop. `grows()` requires both `after.trace_bytes > before.trace_bytes > 0`
and `after.last_cycle > before.last_cycle > 0`. If the initial sample is zero,
no later sample can satisfy that predicate. The observer therefore cancelled
otherwise advancing simulations. The existing delayed-growth host tests did
not cover this initial-empty-trace condition.

The successor must test the actual recorded discovery sequence, establish a
positive baseline within the same original60-second window, then require later
growth with stable PID generation and verified identity. It must not reset the
deadline, loosen the oracle, change RTL or increase simulation budgets.
Review and a fresh output/service are required before any new launch.

Parent observed the service inactive/MainPID0/Result=success/ExecMainStatus0
after this cancellation. Service exit0 alone is therefore insufficient for
acceptance; the campaign's no-abort and functional terminal gates remain required.
