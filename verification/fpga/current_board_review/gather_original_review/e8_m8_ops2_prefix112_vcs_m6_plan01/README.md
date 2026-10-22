# Original E8/M8 VI0 Prefix112 M6 Plan

Prepare-only ownership. No DUT, build, live-process query, FSDB, retry, changed
oracle, shortened history, or increased DUT time budget is authorized here.
`prepared01/ready.json`, when present, records prepared inputs only, not PASS.
Execution requires a separately pinned parent review and direct service owner.

## Reference And Scope

- Accepted-reference entry must be the successor
  `../e8_m8_ops2_prefix112_reference_successor01/READY.json`, SHA256
  `e6962c38c215ec69ec0f0b3aaf5ebadaa9fb33341027a6c8d7f31fba0f135520`.
- The independent audit must bind that same READY and actual complete raw112.
  `replay.py` fails closed unless actual REVIEW/audit hashes are supplied.
- Source/assembly proof and unchanged SoC ELF remain in old prepare01; this does
  NOT treat its preserved `NOT_COMPLETED_WITHIN_BOUND` reference as accepted.
  Original SoC ELF SHA256:
  `a0445bcb877799d488e40f37d7bcbc038d9f0e36a7a60e147ed8baf3c5ea5f74`.
- Exact natural112 calls /111 predecessors, cap1024,114688 results,224 guards,
  112 returned-vstart checks; all7 VL x4 predicates x4 starts, seed0/scalar-slot0.
  VL1024 starts are1,512,1023,1023; no invented warmup or stopped tuple.
- Original13 instructions, target `30803c57` (`vrgather.vi` immediate0), a1 is
  ordinary indices, a6/t3 zero, source[0]=185. Not VX0, VI31, or EI16.

## Strict Runtime Contract

The sealed M6 image, original ELF, source proof, complete reference, independent
review, old dependencies, new worker/checker/Host report and image configuration
are pinned. The original ELF is privately copied by the existing frozen runner.
No new compile/build step exists. The generic CSV gate and original-derived
strict gate both run. Actual console plus `work/run.vcs.log` must have exact112
markers with raw failure veto, including an unterminated `RVV_PERMUTE_DETAIL`.

Strict CSV checks reconstruct full RNG/setup, every actual argument pointer,
the original13 PC/opcode sequence, all vset returns, original target context,
returned vstart, every full-capacity scalar LBU result and both guards per call.
CTRL return0 must come from the original store PC/opcode; subsequent retirement
must be the original side-effect-free park. Old66 markers/results cannot pass.
The upper512 bytes, VL1023 tail, prestart1023, final element enabled/disabled,
all-off1024, and all last-round scalar checks remain mandatory.

The runtime keeps sticky abort through expensive validation and terminal
publication, requires original runner COMPLETE/exact1 result, re-reads disk
plan SHA at the end, and verifies unchanged inputs/image/approval pins.
Service identity uses the trusted user-bus environment, exact MainPID/cgroup,
RuntimeMaxSec10200, KillMode=control-group and Restart=no. No shell child hides
worker ownership. Resource admission runs only after explicit launch approval;
cap24, memory32GiB, and unused reservations count separately from actual simv.

## Host Controls

`test_host.py` generates synthetic Host-only protocol rows, never DUT evidence.
It retains the prior raw/detail monitor, incomplete oracle, encoding/pointer,
data/CSR/guard, image/ELF/plan drift, service, late-abort and terminal tests.
New controls explicitly remove the final80 scalar reads, corrupt the112th
last guard, remove all upper512 results, corrupt high tail/prestart/mask bytes,
swap final enabled/disabled values, truncate to66, use a66 PASS marker, corrupt
the CTRL instruction, and prove the reference step limit is not a DUT limit.
The positive case checks full112 with both generic and strict CSV validators.
The partial-DETAIL test executes only a tiny Host Python process under the
actual frozen monitor and requires immediate failure cancellation.

## Budget And Commands

jobs1; case9000s; service10200s; no automatic retry or FSDB. The reference's
5,050,000 debug steps are REFERENCE ONLY and impose no DUT retirement cap.
Actual reference firmware cost is5,002,732 retired. Prior M6 E8 VX throughput
(2,672,460 /4052.291789s) gives only a conditional7586s estimate; with20%
headroom it is9103s, above9000. At273/s the estimates are18325s/21990s.
The different standard backend is not guaranteed to match either estimate.
The parent must explicitly accept this risk before execution, without changing
the sealed budget or oracle.

Host command (only after formal independent source/reference acceptance):
`python3 -B test_host.py`

Prepare command (no runtime resource/service query or DUT):
`python3 -B replay.py prepare --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out "$PWD/prepared01" --authorize-prepare --reserved-slots 0`

Future execution command is emitted but NOT run in `prepared01/ready.json`.
Parent approval must say `AUTHORIZE_E8_VI0_PREFIX112_ONCE`, bind exact plan/unit,
successor READY and independent REVIEW hashes, and set budget_risk_accepted.
This scope is not full2688, Linux replay, or closure of an unknown historical
stall point. Independent runner review and parent DUT admission remain separate.
