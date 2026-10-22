# M9 Alignment4 Successor Worker

Prepared entry: `worker.py run --plan-sha256 PLAN --review REVIEW --review-sha256 SHA`.
The review must be the actual independent technical admission, not this handoff.
Current user authorization is preserved in `AUTHORIZATION.md`.

- Plan: `prepared01/plan.json`, SHA256
  `80626a24d10affb79c5242eae19b9e849c0841fcceb7441c1bbbf6ba4aaf5e10`.
- Worker SHA256: `73ed6da511c5bf05bb916545309655b2e9b8016ba7b872f909fd079ecaf8391b`.
- Host: `host01.json`, 41 negative rejections, actual process exit 0, command
  `python3 -B verification/fpga/current_board_review/unmasked_strided_alignment_soc_m9_worker_successor01/test_worker.py`.
  Result SHA256 `b8f50316367658c55ee82f297af8d529e343a623f3d87453a0e58783017647a6`.
- Preflight: actual exit 0, 1219 pins verified, command `python3 -B
  verification/fpga/current_board_review/unmasked_strided_alignment_soc_m9_worker_successor01/worker.py prepare`.
  Actual tool receipts: Host `f7a3ce`; preflight `5f1236` (completed exec session 32682).
- Only four unchanged directed ELFs: load/store, each M-mode and resident Sv39.
  697 checks for each load; 698 for each store; 14 restore readback checks each;
  nine actual memory owners each, including seven non-target helpers.
- The frozen runner retains generic trace validation and wraps its count dictionary
  with `status=VALID`. The separate subprocess invokes the reviewed successor
  `checker.py` (SHA797d0f...), which preserves the complete sealed data oracle.
- Actual simulator numeric exit is fsynced to `child_exit.json` immediately upon
  monitor return, before any runner/checker postcheck. A checker exception cannot
  overwrite that receipt. All failure/cancellation paths stop new dispatch.
- Reuses the reviewed terminal publisher and its sticky abort/monotonic deadline
  decision. No timer-thread acceptance race or success overwrite. No retry.
- Controls16 reuse: independent audit `memory_candidate09_controls16/audit_resume01.json`
  SHA1e8a3e..., exact M9 16 cases/310350 rows/all cycles equal M8. Complete, plan,
  input and evidence pins are inherited. No control test is scheduled here.
- Fixed unit `ara-strided-alignment4-m9-02.service`; direct Python MainPID;
  `RuntimeMaxSec=4200`, `KillMode=control-group`, `Restart=no`, local append log.
  Jobs2; 900 s/case; 60 s/checker; 4000 s acceptance deadline.
- One fresh worker admission: actual external simvs + own2 + conservative unused
  reservation margin2 <=24; MemAvailable >=32 GiB. Failed admission stops without retry.

This prepared handoff is not evidence of a launched service or a DUT PASS. A later
`prepared01/launch.json` and independent `startup_observation.json` record actual
launch and one bounded simv/CSV growth observation. Do not poll the long campaign.
