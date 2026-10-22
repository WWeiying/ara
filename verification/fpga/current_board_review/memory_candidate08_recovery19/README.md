# M8 Same-Input Recovery And Regression

The directory name reflects the initial 19-case preparation. The final pinned
plan contains **20 cases**, after adding the separately requested aligned Sv39
resident indexed LOAD. No original inputs, checker, RTL, or old results changed.

Service: `ara-m8-recovery20-01.service`, submitted once, Restart=no,
KillMode=control-group, RuntimeMaxSec=6600. Output: `prepared01/`.
The service directly owns the sealed runner and its children; no nested service.

Execution order:

1. `indexed_prefix_vl3`, alone, same original STORE ELF and checker, 900s.
   Requires actual rc0, raw success/finish, all966 checks, cause6/vstart2,
   prefix poison, same-PC retry, full memory/guards/CSR and successor operations.
2. Only after pilot acceptance, three workers process the remaining19:
   VL9 LOAD/STORE (same ELF/checker914 checks each, 3600s each), aligned resident
   indexed LOAD (same M6 accepted50-round ELF/checker5215 checks, 2400s), and
   all16 M7 controls (same ELF/console oracle, 180s each).

The original M7 indexed TIMEOUT and diagnostic are unchanged. No misaligned
indexed LOAD variant is launched by this plan. That future software requires
the specified partial-destination exception oracle and a separate preparation.

Exact inputs:

- Plan SHA: `62f4e876969ab8389c43171917ee85c4c3e2b0fc4c86a4c7423ee926578b58fa`.
- 2192 input pins, verified before execution and before aggregate acceptance.
- M8 image SHA: `bd27bf6f7bb90b2b05c4546faaed8a8e32b8e545c182167fef72c170e40bdfd0`.
- Reviewed AddrGen SHA: `1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2`.
- 539-file membership retained; only this RTL differs, plus byte-checked exact
  root relocation in frozen.filelist/hardware/bender. Config digest unchanged.
- Worker SHA: `01242737beef2237702df8f5542ab6c88f821251507cb244749f0d8d86543ee0`.
- Host02: actual exit0, 11 focused tests. Host01 and both preparation refusals
  remain recorded; see `PREFLIGHT_REFUSALS01.md`.

Every child outcome is saved before artifact/checker processing. Any timeout,
nonzero/unknown/bool return code, software failure, checker rejection, pin drift,
partial membership or sticky cancellation prevents acceptance and stops work.
No retry. Child-process timeout budgets are unchanged; 6600s is the combined
service ceiling, not an increase to any testcase timeout.

All16 controls compare every CSV event with their actual M7 baseline. The aligned
resident LOAD compares every CSV event with its accepted M6 baseline. Noncycle
differences reject acceptance; every cycle-only difference is retained in
`cycle_differences.csv` and reported, never silently declared performance-equal.
The original resident checker additionally enforces full memory/PTE coverage,
50 rounds, no faults, and all5215 checks. References do not replace DUT evidence.

Startup proof: `prepared01/startup_observation.json` records one actual owner,
simv argv/private ELF, CPU and trace-size growth observation. It is not PASS.
Terminal evidence will be `prepared01/complete.json` with actual child receipts,
strict checker results, full comparison outputs, and evidence hashes.

Already submitted command (do not launch again):

```sh
python3 worker.py run --plan-sha256 62f4e876969ab8389c43171917ee85c4c3e2b0fc4c86a4c7423ee926578b58fa
```
