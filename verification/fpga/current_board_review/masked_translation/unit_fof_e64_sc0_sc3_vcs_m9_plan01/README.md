# M9 e64 sc0/sc3 Two-Case Worker

Independent successor to `unit_fof_e64_suffix_two_vcs_m9_plan01`. No old input
or output is modified. Exact reference READY:
`8c2f89e677e1cf6148ad3d1013f1598a91ed77506a73266603d956ffe9672e1e`.
Frozen M9 image SHA:
`48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`.

sc0 target starts at VL8/maskff, returns VL4/start0 and leaves only the original
four final tail words undefined. Original helper restores VL8 for full output
store. sc3 ordinary load starts VL8/mask0 on protected page, retains VL8/start0,
and all eight results remain strict. Full original oracle and four nonempty
memory owners (including three non-target helpers) use the frozen new reference
checker directly. Generic trace validation remains additional, not a substitute.

jobs2, case1800s, worker3900s, service4200s, cap24 live+reserved, >=32GiB available.
No build/FSDB/retry. Runtime IDs are separate from original Linux names.
Numeric monitor and child outcomes are durable before postchecking; raw FAIL
veto, late-abort publisher, pins and exact metadata gates are unchanged.
`delta_check.py` checks17 mature functions structurally; it is not another
execution of the predecessor Host tests. The prior44-test evidence is pinned.

Prior sc1/2 collector acceptance is mandatory: result SHA
`e5339c29d0a7d516df5b8053d79e5be545f547ecc8bd5cabbcb66dc12200043c`,
exact two numeric0 members/noabort/no retry, actual systemd exit facts, and all
790 prior evidence pins. The worker is the direct service MainPID. ExecStopPost
uses the unchanged tested predecessor hook and writes actual systemd-injected
EXIT_CODE/EXIT_STATUS/SERVICE_RESULT, never GC defaults.

Only the final independent Tesla review can authorize launch. Launch envelope
also pins hook/plan/dryrun identities. One actual fresh resource admission;
one bounded two-sample real simv/CSV-growth observation, then no polling.

Entry points: `replay.py prepare`, `replay.py dryrun`, `service_launch.py prepare`,
`service_launch.py launch`, then `observe_startup.py` once. The exact plan,
launch envelope and independent review hashes are required. This is exactly
two source-derived Sv39 singles, not Linux closure or previously tested sc1/2.
