# One Actual M9 Full4095 Launch

Exact frozen plan: `prepared01/plan.json`, SHA256
`4df0c5b631b8645fb51a4ca52ca1bb916dec03ad455e88c0a380a5b023f2c2db`.
Tesla entry: `../full_e8_m4_dict_worker_entry01/ENTRY02.json`, SHA256
`19f59be98675689597cc880b0884a4020a139f8f1af4aaf1db18fb5f2cba5b22`.
Dryrun SHA256: `4525e7ac7a4f758017fcb2a8223df0af8abd4417adfd75988e96d3c1638ae71e`.

The sole actual service is
`ara-arithmetic-original-e8-m4-full4095-m9-01.service`.
Actual systemd submission child returned0. Worker PID2971257, simv PID2971279.
Two fixed startup samples confirmed CPU ticks800->1306 and CSV bytes
319488->622592. No active CSV content was read. The actual executable matched
frozen M9, all PRELOAD/TESTCASE/TRACE arguments matched, the private ELF SHA
matched154def073e4bc0282b6b72103314dec2b3d6f4229ff3564228400fa4c89ecc14,
and simv belonged to the actual worker service control group.

Actual fresh admission observed17 existing external simv processes, jobs1,
unused reservation0, total18<=24, available memory112315129856 bytes (above
32GiB). This does not reserve unused future launches. The fixed bounds remain
10800s case/12000s worker/13200s service; stop timeout360s.

The frozen ExecStopPost event hook is attached to this actual service. It saves
actual SERVICE_RESULT/EXIT_CODE/EXIT_STATUS before launching the independent
metadata-only terminal collector (300s). Collector acceptance requires whole
producer PASS, actual numeric monitor0/no timeout/no failure/no cancellation,
full4095 strict/generic/required-owner closure and unchanged pins. No second
semantic CSV parse, reference, image build or DUT retry is arranged.

Authoritative startup receipts are `prepared01/launch_invocation.json`,
`service_submission.json`, `launch.json` and `startup_observation.json`.
After exit, authoritative event facts will be `service_exit.json`,
`collector_exit.json` and `collector_result.json` in prepared01. They are not
claimed to exist or be accepted at startup. DUT acceptance remains pending;
the original Linux historical stall is not declared closed.

All consumed worker/source/reference/image files are frozen. No further
progress polling is authorized or required by this launch receipt.
