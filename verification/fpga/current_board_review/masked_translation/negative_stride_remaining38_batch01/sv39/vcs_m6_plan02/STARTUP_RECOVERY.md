# Startup-Only Successor

Plan01 `cf1358b4511d3c40e15ba0368cd025e0d89bc8e4bebcc5320ab6e54f84330974`
failed at its first user-service identity query, before resource admission,
`launch.json`, replay dispatch or any DUT child. Original service log and
`startup_confirmation.json` remain untouched. The systemd start-request rc0
was not a worker success. The first query's stderr was not persisted.

Inspection of the same `integration/run.py:environment()` returned both
XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS absent. Plan02 follows the
existing pilot's explicit trusted user-bus environment for `systemctl` only.
It does not change the simulation environment, testcase, budget, pins policy,
result oracle, or retry policy. A Host test starts with an empty environment
and verifies the query receives both correct variables and full owner gates.

`csv_check.py` remains byte-identical:
`933399985d3b4508ded433445935fcaa2512f08e8ebd5f9acd46026ab2fc5420`.
`test_host.py` remains byte-identical:
`d1022d86fb9e684b3931af4dee07af2a3cd9c245bf0dd2777730a4a7e58a4bbb`.
Copied Host9 log/receipt records the original plan01 execution, not a new run.
The new runner Host receipt is separate. All 20 software/reference ELFs and
the complete38 source/reference READY are unchanged. No DUT retry occurred.
