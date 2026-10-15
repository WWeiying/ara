# Actual M9 Continuous1134 Startup

Exactly one submission: ara-whole-continuous1134-m9-01.service.
Launcher actual wait exit0; systemd submission actual0. No retries.
Worker MainPID2918330 directly owns the service; simv PID2918339 is in
the same control-group with the M9 executable and exact private ELF/trace.

Two fixed samples,5.090s apart:

| Evidence | First | Second |
| --- | ---: | ---: |
| simv CPU ticks |1148|1653|
| CSV bytes |581632|929792|
| Complete cycle |7932|12063|
| Complete retirement order |5279|8404|

Admission counted5 other live simv plus this job =6/24, reserved0;
MemAvailable119534764032 bytes. No other simulation was changed or polled.
Budgets remain case10800,worker12000,service RuntimeMax13200 seconds.

Bindings:
- Plan dda443312e22010c1b68a0090032d15682049c554b1cc879f780444ca10ca51d
- Tesla ENTRY04 8a09c45d9aab946a13efa43f600e094b8568e4a418f1f98dc9591bd48cdb4a72
- Startup receipt dc8123adca3f14a8db6edfda084492f1e69165453dc74ab533d07b3a3d8a646d
- Admission receipt 116174be24e9b7ddd941ef976868e979bbef22666c0b83b97e15dbc7456af6da
- Submission receipt 7cd184cd2c74e2e2e544c601acdbe85ff24f1bac26a80d8fd9064b739fb43a88
- Launch command receipt c242c10b8a1c7dba2bad56a99b759d5340a069f9e30d38f26e9776e8fb86cb8f

This is actual startup only, not DUT acceptance. No further polling.
After numeric simulator wait0, the worker runs the one-pass generic+strict
full continuous1134 audit. Failure retains first row/cycle/PC/call context,
numeric outcome and raw artifacts; no retry/timeout extension/RTL change.
ExecStopPost records real service exit and invokes the pinned metadata-only
collector once, with actual collector wait status saved. Acceptance still
requires whole1134 full oracle/owner completion, no abort, unchanged pins,
numeric exits and collector success; no inference from startup or markers.
