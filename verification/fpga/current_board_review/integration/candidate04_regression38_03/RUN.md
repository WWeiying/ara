# Candidate04 Unchanged38 Regression

The current comparison-source repair is tested with the same38 accepted
candidate02 ELFs, full software oracles and individual time budgets. There is
no rebuild. The representative candidate04 controls and source-specific tests
have passed; this batch checks their integration with the earlier arithmetic,
slide, reduction and extension repairs.

- Service: `ara-candidate04-arithmetic38-03.service`.
- Driver: `../replay_candidate04_regression_final.py`.
- Plan SHA256: `6a4b74d7bea9025771fcfb4e48204b58b5bfc80f40450eeec7e0e4f900cc93b9`.
- Image JSON SHA256: `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
- Four jobs; original per-case budgets180..1200 seconds; service limit7200s.
- First failure stops dispatch; no automatic retry.
-17 host checks and38 dry-run commands passed before launch.

The first four real simv PIDs were57798,57799,57800,57801. Each used this
directory's private input ELF and commit trace and the frozen candidate04
image. Two startup observations showed increasing retired-event cycles:

| Case | First observation | Later complete CSV row |
| --- | ---: | ---: |
| extension-original__extension_overlap_vl127 |2092 |33133 |
| large-offset__e8_m4_single |2472 |81435 |
| large-offset__e8_m8_single |2361 |83705 |
| large-offset__e8_m4_sequence |2247 |79959 |

These are startup/progress observations, not terminal acceptance. Inspect
`complete.json` and all raw test results after the service finishes. Earlier
`candidate04_regression38_01` and`_02` are unlaunched preparation records;
their scripts/plans were retained when review strengthened the final checker.

```sh
systemctl --user status ara-candidate04-arithmetic38-03.service --no-pager
tail -n 20 verification/fpga/current_board_review/integration/candidate04_regression38_03/service.log
```

No whole historical matrix or original Linux ELF acceptance is inferred from
this38-program integration regression.
