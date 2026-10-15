# Prepared01: Blocked, Not Launched

The original ready command had `Type=exec,RemainAfterExit=yes`. Main-process
success would leave the unit active(exited), so `ExecStopPost` would not run
automatically. This is a real harness lifecycle gap, not a DUT failure.

Prepared01, original worker and Host01/02 evidence remain unchanged. No service
was launched. `replay02.py` is an unused exploratory draft and is not the final
worker. The successor uses the unchanged `replay.py` (88d7d147...) with a fresh
plan and launch argv setting `RemainAfterExit=no`.

`prepare_launch02.py` only constructs the fresh service contract/ready command,
then actual no-build dryrun. The original strict checker and worker are not
rerun as a DUT or reference; the28 Host tests are not repeated. The new automatic
stop hook persists actual systemd exit facts and runs one bounded metadata
collector. Its numeric wait is separate from the producer and simulator exits.
No human stop of a successful service is used to manufacture automatic closure.

Independent exact successor review and a separate parent run authorization
remain mandatory. No launch is authorized in this preparation turn.
