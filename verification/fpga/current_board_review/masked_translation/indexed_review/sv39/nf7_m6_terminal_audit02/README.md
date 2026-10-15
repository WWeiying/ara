# NF7 M6 Terminal Audit Preparation

Preparation only. Starting the event waiter requires a separate parent authorization.
No simulator is launched or controlled by these tools. All production/sealed files stay unchanged.

This audit binds plan02 `eebd310b9b9ccdf5b5ca398d556b2a7b6d07746c0f4149972130716ab7481cc0`,
actual parent `80c8d257fbbfcb917287668e9da308867ff2b0ea26ad2478ec75a08d23777852`,
actual launch `8427a10c7a2c6e9eba928ae5e1e2678463afc6766787c8356a736df3195509aa`,
M6 image `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
The launch's current, independently accepted NF2 full40 evidence is pinned; no early
NF2 preparation or incomplete-state attestation is substituted.

Prepare commands (no live NF7 output/CSV reads):

```sh
python3 -B test_host.py
python3 -B audit.py prepare
```

Future parent-authorized waiter command, not invoked by preparation:

```sh
python3 -B wait_terminal.py --authorize-wait PREPARED_SHA
```

Use a NEW direct service with Restart=no, KillMode=control-group, RuntimeMaxSec=27000,
working directory here and stdout/stderr append to this directory's service.log.
Offline-only bounds:18000s event wait,7200s total audit,600s per isolated CSV audit.
These never modify the running DUT's2400/2700/16200/16800-second limits.

The accepted inotify/pidfd routine waits without periodic polling. Actual whole24
COMPLETE/PASS, strict numeric child0, noabort/retry, exact members, current private
ELFs/image/commands and unchanged full evidence pins are prerequisites. Only then
bind actual complete SHA and execute once. Every CSV is parsed once, unchanged rows
feeding both original NF7 checker and frozen generic validator; independent PC/code
matches the ELF. Fail first, preserve evidence, never retry or read remaining CSVs.

Final scope is24 unchanged ELFs/96 source trials/284816 comparisons/168 checkpoints/
72 architectural faults/96 S-ecalls. Preserve original context, partial-field rules,
tails, guards, memory, trap/restart/PTE and existing CSR checks. No new restore-readback
claim or Linux exact-failure closure. Numeric simulator outcome, audit subprocess exit,
and UNKNOWN historical outer service exit are separate evidence.

Outputs are new `wait01` and `terminal01` only after authorization. Actual subprocess
PIDs/commands/wait returncodes, lossless digests, pre/post pins and REVIEW are retained.
