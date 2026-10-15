# Independent Gather75 Terminal Audit

Date: 2026-10-11. Verdict: **PASS**, with no remaining independent review blocker
for parent-coordinated arithmetic prefix5 admission. This document records the
completed read-only audit; writing it did not repeat tests or simulations.

## Identity

Output: `remainder75_01/vcs_candidate04_01/`.
Frozen image: `/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image`.
Image ledger SHA256:
`e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.

| Artifact | SHA256 |
| --- | --- |
| `remainder75_01/plan.json` and output `plan.json` | `116e89a3b9466ae910926653f1a84abb9c480c7dc12a9aca77ba81f5e76b2f83` |
| Output `complete.json` | `9b71c95ad9df4e32beb84d88407c40ff5368bfb311bdfa6ae4897de7afd551f6` |
| Output `worker_exit.json` | `778418cf4515631620c6a266d17651181629ee966ae056c5db95b8ff58e36bc5` |
| Canonical recomputed results array | `40421de116f903c2cb07131c9758e4c23aeec8d2a8a4678c729e3f2cd0388d2b` |

The in-memory audit summary SHA256 reported to parent was
`292293c9b0c50ac7f38be40085e4d61d74287549f5b7507894a8ba7a3aa46f48`.
That digest identified the transient audit object, not a previously saved file
and not this Markdown document. Canonical JSON digests used sorted keys and
compact separators. The unchanged `complete.json` above is the durable terminal
evidence anchor.

## Independent Checks

- Imported `check_remainder75.validate(out, plan_sha256)` with Python bytecode
  writes disabled. Did not call `checker.main()` or any save function.
- Recomputed all 75 results and compared them exactly with existing
  `complete.json`; checked its SHA before and after. No terminal overwrite.
- Verified all 3972 pinned inputs and 378 prepared files. For every source port,
  reversed the six bounded-loop substitutions and compared the result with the
  standard adaptation of its source `scenario.c`; verified archived source-copy
  hashes. Original initialization, operation sequence and full scalar oracle
  remained intact.
- Confirmed exact disjoint accepted8 plus remaining75 membership, totaling 83
  source singles. The accepted8 were not rerun. Stage order was first12 followed
  by remaining63, with strict first-stage acceptance required.
- Revalidated 150 raw logs, exact success markers and failure vetoes, 75 private
  ELF/image/command identities, and 75 CSVs. Each target PC/encoding appeared
  once with VL2/vstart1, returned vstart was zero, and traces had no CVX exception.
- Full-capacity scalar observations covered 7792 elements and 150 guard reads.
  Stored stage gates and the terminal result array matched the recomputation.
- Both stages had exact COMPLETE membership and PASS counts, runner returncode0
  and error=None. Worker returncode0/error=None, retries0 and accepted8_rerun=false
  matched the plan. Strict checker and service logs recorded
  `PASS_8_ACCEPTED_PLUS_75_SOURCE_SINGLES_CANDIDATE04`.
- Per-case measured elapsed time ranged from 23.171842873096466 to
  54.03404317703098 seconds, below the fixed 300-second limit.

## Exit Evidence and Limitation

The one-time systemd query reported the collected unit as not-found,
inactive/dead. **Missing-unit state is not proof of successful process exit.**
`journalctl --user` was denied access; no journal-based exit evidence is claimed.
Acceptance rests on the actual case/stage/worker returncodes, raw evidence and
successful strict terminal checker described above.

A separate single read-only `/proc` inventory found no process in the Gather
service cgroup and no simv using this output path; there were no unreadable
processes in that inventory. This supports release of Gather's resource slot,
not a substitute for the functional acceptance checks.

## Scope and Handoff

This establishes accepted8 plus 75 genuine source single ports on candidate04.
It does not close the full parent matrices, original Linux execution, or the
separate stalled records. No RTL, sealed sources, pins or logs were changed;
no host, Spike or DUT tests were rerun for this audit.

The audit also read the existing candidate04 regression38 PASS terminal and NF8
jobs8 admission worker record. Their SHA256 values were respectively
`b670ef92e9bf439ac0969497bb7fb0acce1108a5c18f7ec16533f22b5d855c13`
and `dda1d45b1680a9336380cf87e7fafa1ac16b1a9e578bcf473a324ddfff452b00`.
These satisfied the previously agreed ordering prerequisites; they were not
new revalidations of either suite. Parent retained launch/resource coordination.

Parent subsequently reported starting prefix5 under
`ara-arithmetic-prefix5-candidate04-01.service`, with two jobs and a 10000-second
outer limit. This is a parent-reported handoff only: this auditor did not launch,
repeat startup confirmation, or poll that service. FP2 remains separately held.
