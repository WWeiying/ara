# Plan08 Startup Confirmation

Parent launched `ara-fp-original-restart-candidate04-02.service` at
2026-10-11 04:56:20 PDT after independent review of the dependency-gate fix.
Plan SHA256: `011540f110776d0c9296924f6d677f6c43ce8619ebaabd1f4b93d8f77b5b054a`.
Parent approval SHA256: `f60b02bef9fb251da06fa2093f4c6da97c95cbbd591a3eb86ba5964cd536ad2d`.

The service directly owns its worker and simulators, with KillMode=control-group,
Restart=no and RuntimeMaxSec=4500. Each test retains the reviewed3600-second
budget. Output is `candidate04_restart_run04/`; old plan07 failure remains.

Read-only startup inspection found both actual simulators in the expected
service cgroup, executing frozen candidate04's `campaign/image/_build/vcs/simv`
with their own `input.elf` and separate working directories:

| Test | PID | CSV bytes before/after | Complete event cycle before/after |
| --- | ---: | --- | --- |
| restart_e16m2_prefix130 |151096|2138112 /2322432|26375 /28507|
| restart_unmasked_e16m2_prefix130 |151097|1953792 /2146304|23370 /25299|

The samples were separated by two seconds. These observations establish
startup and progress, not correctness or expected completion time. No long
polling was performed. The682-call prefix remains held and was not launched.
Acceptance still requires the strict terminal validator, exact traces and
unchanged pins; a service's active state is not a PASS result.
