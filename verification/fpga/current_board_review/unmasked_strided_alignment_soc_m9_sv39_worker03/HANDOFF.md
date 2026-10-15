# Two Undispatched Sv39 Members

Only `load_sv39` and `store_sv39` from the original four directed fixtures.
No replay of the accepted M-mode closed CSVs or independently accepted controls16.
Same original source/ELF/oracle and frozen M9 image. Original failed batch is untouched.

- Worker SHA: `07fe41ae7fc6e69ec37ef1b17dc83b6ddb6567594586700ff2ac574ec76edd05`.
- Plan: `prepared01/plan.json`, SHA
  `83a427884a035b7deda1923dd1000e6fc4043584306a15561f6c34fe8bc8d752`.
- Actual preflight exit0, 1262 verified pins (tool `b8e660`, session43950).
- Host: 41 negative rejections, actual exit0 (tool `998319`), `host01.json` SHA
  `52e4208aa08c52ecd1ae17d28dda59e3522a2cc594c8c375b6fd2b989e30ac97`.
- Actual CLI binds endpoint02 checker SHA
  `8d26dcfc02ee9e7a2cf5b6faa2d52ce0c725347c5d6adbefd1c5370a6f96b604`.
  The pinned ELF defines each backend exit; no fake/optional HTIF symbol is added.
- M-mode admission requires exact closed-audit SHAfb29028..., actual recorded audit
  outcome, two exact accepted members, original child numeric0 receipts, output
  hashes, 697/698 full checks and 9/7 memory/helper owners. No old ERROR is relabeled.
- Original generic six-event trace validation, complete unchanged scalar oracle,
  numeric-first receipt, command/private ELF/image pins, raw log veto, owner gate,
  first-failure stop and reviewed terminal publisher remain active.
- Service `ara-strided-alignment-sv39-m9-03.service`, direct MainPID, jobs2,
  900 s/case, 60 s/checker, 4000 s acceptance deadline, service4200 s,
  `KillMode=control-group`, `Restart=no`, local append `service.log`.
- One fresh admission: actual external simvs + own2 + conservative reserved2 <=24,
  MemAvailable >=32 GiB. No admission polling/retry.
- Runtime output: `prepared01/sv39_2/tests/strided_alignment_{load_sv39,store_sv39}/`.
- Eventual terminal: `prepared01/complete.json`; first error `prepared01/firstfailure.json`.

This handoff alone is not a launch receipt. After concrete independent entry
admission, bind the actual review path/SHA in `worker.py run`. Actual startup is
recorded separately in `prepared01/launch.json` and `startup_observation.json`.
Do not poll the campaign after the single bounded startup observation.
