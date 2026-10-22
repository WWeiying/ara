# Actual Startup Confirmed, Not DUT PASS

- Service: `ara-strided-alignment4-m9-02.service`.
- Actual direct worker MainPID: **2710729**.
- Observed actual simv PIDs: **2710755**, **2710756**, matching this service cgroup,
  private `input.elf` and owned `+COMMIT_TRACE` paths.
- One bounded five-second pair of samples: CPU ticks increased **507** for each;
  CSV bytes increased **360448** and **356352**, respectively.
- Receipt: `startup_observation.json`, status
  `ACTUAL_SIMV_AND_CSV_PROGRESS_NOT_PASS`. Startup observer actual exit **0**.
- Independent technical admission:
  `../unmasked_strided_alignment_repair_zeno01/M9_ALIGNMENT4_WORKER_ENTRY01.json`,
  SHA256 `c8f753bc294c190de56de0c9a14a45a0124a32f9db5a9f9d50aabed6434219bb`.
- Plan SHA256: `80626a24d10affb79c5242eae19b9e849c0841fcceb7441c1bbbf6ba4aaf5e10`.
- Actual launch/pins/resource receipt: `prepared01/launch.json`.
- Appended stdout and stderr: `service.log`.
- Case outputs: `prepared01/alignment4/tests/strided_alignment_{load_m,store_m,load_sv39,store_sv39}/`.
- Eventual aggregate: `prepared01/complete.json`; any first error is retained in
  `prepared01/firstfailure.json`. No terminal result was inferred at startup.

Actual `systemd-run --user` returned exit0, tool receipt `bb32cb`; service budget
4200 s, `KillMode=control-group`, `Restart=no`. The reviewed worker command includes
the exact plan SHA and actual review path/SHA above. Numeric child exits are separate
from postchecker exits. Only alignment4 is scheduled, jobs2, 900 s/case; controls16
are reused accepted evidence and are not rerun.

Startup observation command:

```sh
python3 -B verification/fpga/current_board_review/unmasked_strided_alignment_soc_m9_worker_successor01/observe_startup.py
```

Actual exit0 receipt `7c4465` (exec session 38050 completed). The observation reads
bounded CSV tails only, not a full oracle parse. No further background polling,
retry, reference, build, production RTL change or previous sealed-file edit.
