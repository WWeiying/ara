# M6 Service Exit Witness (Awaiting Parent Review)

Scope: keep an existing systemd object referenced and record exit facts only.
No restart, stop, kill, service-property change, DUT launch or functional oracle.
Do not interpret witness process exit zero as DUT PASS.

Read-only local introspection confirmed Manager methods `RefUnit(s name)`,
`UnrefUnit(s name)` and `GetUnit(s name) -> o unit` on the user bus. Python is
`/usr/bin/python3`, dbus module `/usr/lib64/python3.9/site-packages/dbus/__init__.py`.
The persistent `dbus.bus.BusConnection(unix:path=/run/user/1002/bus)` is essential;
a short-lived busctl reference would disappear with its connection.

## Identity And Lifetime

The helper accepts only `ara-indexed-overlap-m6-01.service`, initially active,
MainPID 620452, exact user-1002 app.slice cgroup and InvocationID
`94f592605b7147d3b5e47923457f3078`. It checks the pinned worker plan SHA
`d2053cb571e3df53a4ec846d440b0eb3eca72f61b4b048ecad196060ac7903b8`.
It rechecks invocation after RefUnit to reject an intervening exit/reload race.
Missing/collected/restarted units are errors, never synthesized success.

Fresh direct output contains exclusive startup.json, then exclusive actualexit.json
once inactive/failed with MainPID zero, including non-success. The record contains
raw Result, ExecMainCode/Status, start/exit timestamps, Id and InvocationID; missing
exit fields explicitly make exit_evidence_complete false. No PASS marker exists.
Properties are read every 120 seconds, each D-Bus RPC has a 10-second timeout.
Nominal hold budget is 18000 seconds; in-flight reads/cleanup can add up to 40 seconds.
No expensive DUT artifacts or CSVs are read while holding the reference.

After recording exit, retain until `repair06_followup/fresh02/complete.json` exists
(success or failure), signal cancellation, or hold budget expiry. File existence
is solely a release condition, never a functional verdict. SIGINT/SIGTERM request
shutdown; finally performs UnrefUnit and closes the private connection even if
UnrefUnit fails. Connection teardown also releases references on abrupt death.

## Evidence

`python3 -B -m unittest -v test_witness`: four tests passed, including both exit
statuses, initial identity rejection, exclusive-write failure cleanup, cancellation.
Parent authorized harmless live demos only. `python3 -B demo.py` completed:

- `demo01/exit0.json`: retained loaded/inactive, ExecMainCode=1, Status=0,
  ExecMainExitTimestamp=1791753343004270.
- `demo01/exit7.json`: retained loaded/failed, ExecMainCode=1, Status=7,
  ExecMainExitTimestamp=1791753348143641.
- `demo01/released0.json` and `released7.json`: NoSuchUnit after closing the
  reference-owning connection. Both demos used sleep 3 and RuntimeMaxSec=20,
  --collect; no simulator, hardware or license use. No demos remain running.

## Proposed Launch (Not Executed)

Only after parent review/authorization, run as a separate owned witness service:

```sh
XDG_RUNTIME_DIR=/run/user/1002 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1002/bus \
systemd-run --user --unit=ara-indexed-overlap-m6-exit-witness01 \
  --property=RuntimeMaxSec=18060 --property=KillMode=control-group --property=Restart=no \
  /usr/bin/python3 -B \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/indexed_overlap_original/repair06_exit_witness01/witness.py \
  --out /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/indexed_overlap_original/repair06_exit_witness01/run01 \
  --authorize-refunit
```

No actual M6 RefUnit call or witness launch has been performed in preparation.
This does not guarantee admission by any observer or recover a unit already GC'd.
