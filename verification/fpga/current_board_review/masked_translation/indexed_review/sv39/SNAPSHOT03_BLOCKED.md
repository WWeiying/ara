# Snapshot03: PAM Fixed, Real Admission Refused

No VCS, service, RTL, fixture, or oracle change was launched. Sealed plan01 and
plan02, their helpers, and their refusal logs remain unchanged.

The new `successor_snapshot03.py` replaces only the process snapshot in the
accepted gate02 worker. It reads comm/cgroup/argv before exe/cwd; irrelevant
processes do not require protected symlink access. Simv or known NF2/arithmetic
cgroup/argv matches still require accessible exe/cwd. Permission failures that
prevent classification remain refusals, not blanket ignores.

`snapshot03_host_tests.json` records eight negative rejections and a real-host
PAM positive: PID 624598, UID 1002, `(sd-pam)`, user-manager `init.scope`, no
exe/cwd access. Simv, renamed simv argv, NF2/arithmetic cgroup or argv ownership,
inaccessible cwd, and unreadable classification metadata all remain fail-closed.

The single real read-only capacity gate was executed after inherited pin/image
checks and 24 dry runs. It passed the PAM classification but refused admission:

```
Terminal arithmetic still owns processes or another simv exists
```

Raw result: `vcs_plan03/real_capacity_gate.json`. The error occurred in the
unchanged terminal-arithmetic admission rule, not `/proc/.../exe` access.

A separate, single post-refusal inventory (not another gate attempt or progress
poll) is preserved as `vcs_plan03/post_refusal_processes.json`. It observed five
external simvs under `/user.slice/user-1002.slice/session-17.scope`:

| PID | External Build |
| --- | --- |
| 3987890 | `ara_reduction_optimization/hardware/build/rce/gap_word_sparse_soc_on_v1` |
| 3999529 | `ara_reduction_optimization/hardware/build/rce/gap_split_credit_off_v1` |
| 3999776 | `ara_reduction_optimization/hardware/build/rce/gap_split_credit_on_v1` |
| 4000250 | `ara_reduction_optimization/hardware/build/rce/gap_split_credit_off_v1` |
| 4000254 | `ara_reduction_optimization/hardware/build/rce/gap_split_credit_on_v1` |

These do not belong to the approved arithmetic service. Five existing simvs plus
four NF7 workers would also exceed the eight-slot limit. This inventory describes
the post-refusal instant, not an exact reconstruction of the earlier gate instant.
The external processes were neither signaled nor otherwise modified.

No successful real capacity preflight is claimed. Plan03 preparation stopped
before creating `plan.json`, `preflight.json`, or `worker.json`; its partial
output and evidence are preserved. No launch command is proposed. A later
authorized admission attempt needs a fresh output and an explicit parent
capacity decision; no polling, automatic retry, weakened gate, or timeout change
has been introduced.
